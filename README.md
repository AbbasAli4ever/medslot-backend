# Clinic Appointment Booker: API

Django REST Framework backend for booking, listing, cancelling and completing clinic appointments.

The Next.js frontend lives in a separate repo: https://github.com/AbbasAli4ever/medslot-frontend

## Quick start: run both apps

Clone both repos side by side:

```bash
git clone https://github.com/AbbasAli4ever/medslot-backend.git backend
git clone https://github.com/AbbasAli4ever/medslot-frontend.git frontend
```

**First time only**

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
```

**Every time**, in two terminals:

```bash
# Terminal 1: backend, http://localhost:8000
cd backend
source .venv/bin/activate
python manage.py runserver 8000
```

```bash
# Terminal 2: frontend, http://localhost:3000
cd frontend
npm run dev
```

Then open:

- App: http://localhost:3000 (click **Continue with demo account**, or log in with `staff@medslot.app` / `medslot123`)
- Swagger: http://localhost:8000/api/docs/ (call `POST /api/auth/login/`, then click **Authorize** and paste the token)

**Troubleshooting**

- "Port already in use": stop the old process with `lsof -ti tcp:8000 | xargs kill` (backend) or `lsof -ti tcp:3000 | xargs kill` (frontend).
- To clear all appointments, restart the backend (Ctrl+C, then `runserver` again). Data is kept in memory only.

## Run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver 8000
```

Optional environment variables are listed in `.env.example`. No migrations are needed because there is no database.

- Swagger UI: http://127.0.0.1:8000/api/docs/
- OpenAPI schema: http://127.0.0.1:8000/api/schema/

## Run with Docker

`docker-compose.yml` starts both apps. The backend and frontend are separate repos, so clone them side by side:

```bash
mkdir medslot && cd medslot
git clone https://github.com/AbbasAli4ever/medslot-backend.git backend
git clone https://github.com/AbbasAli4ever/medslot-frontend.git frontend
cd backend
docker compose up --build
```

- API on http://localhost:8000 (Swagger at `/api/docs/`), web app on http://localhost:3000.
- The frontend is built from `../frontend` by default. Point elsewhere with `FRONTEND_DIR=/path/to/frontend docker compose up --build`.
- `web` is built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api`, because the browser calls the API from the host.
- `api` reads `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` from the environment (set in the compose file).
- API only: `docker compose up --build api`.
- The API container runs Django's `runserver --noreload` on purpose. The store is in memory, so it must be a single
  process; a multi-worker server would give each worker its own data. Data resets when the container restarts.

## Tests

```bash
python manage.py test
python manage.py spectacular --validate --fail-on-warn --file /dev/null   # schema check
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login/` | Staff login: `{email, password}` returns `{token, user}` |
| GET | `/api/auth/me/` | The logged-in staff member (401 without a valid token) |
| GET | `/api/doctors/` | The fixed list of doctors |
| GET | `/api/appointments/` | Paginated list, sorted by date then start time. Filters: `doctor`, `date`, `status`, `search` (patient name or phone). Paging: `page` (default 1), `page_size` (default 10, max 50) |
| POST | `/api/appointments/` | Book an appointment (201). **Staff login required** |
| GET | `/api/appointments/{id}/` | One appointment (404 if missing) |
| PATCH | `/api/appointments/{id}/` | `{"status": "cancelled"}` or `{"status": "completed"}`. **Staff login required** |
| GET | `/api/appointments/available-slots/?doctor=1&date=YYYY-MM-DD` | Free 30-minute start times, 09:00 to 16:30 (the `free` slots of the day view) |
| GET | `/api/appointments/doctor-day/?doctor=1&date=YYYY-MM-DD` | Doctor's day: every 30-minute slot with its status and appointment |

The list is always paginated. Filters and sorting apply first, then the page is cut:

```json
{"count": 26, "page": 1, "page_size": 10, "total_pages": 3, "results": [{"id": 1, "doctor": 1, "...": "..."}]}
```

`total_pages` is at least 1, so no matches gives `{"count": 0, "page": 1, ..., "results": []}`.
A page past `total_pages` returns `404 {"detail": "Page 5 does not exist."}`. A bad `page` or
`page_size` returns 400 with field `errors`.

The doctor's day view lists all 16 slots (09:00 to 16:30) for one doctor and date:

```json
{"doctor": {"id": 1, "name": "Dr. Ali", "specialty": "Cardiology"}, "date": "2026-11-10", "is_open": true,
 "summary": {"free": 13, "booked": 2, "past": 1},
 "slots": [{"start": "09:00", "end": "09:30", "status": "past", "appointment": null},
           {"start": "09:30", "end": "10:00", "status": "booked",
            "appointment": {"id": 4, "patient_name": "Ayesha Khan", "start_time": "09:30", "end_time": "10:30",
                            "duration_minutes": 60, "status": "booked"}}]}
```

- `booked`: a booked or completed appointment overlaps the slot (completed ones show `appointment.status: "completed"`).
  A 60-minute appointment covers two slots and both reference it. Cancelled appointments leave the slot free.
- `past`: free, but the slot has already started (earlier today, or any slot on a past date).
- Sunday: `is_open: false` and `slots: []`. Both `doctor` and `date` are required (400 otherwise).

Example booking body:

```json
{"doctor": 1, "patient_name": "Ayesha Khan", "patient_phone": "03001234567",
 "date": "2026-11-10", "start_time": "10:30", "duration_minutes": 30, "reason": "Follow-up"}
```

## Staff login

Only logged-in staff can book, cancel or complete appointments. All GET endpoints are public.

- Demo credentials: `staff@medslot.app` / `medslot123` (override with `STAFF_EMAIL` and `STAFF_PASSWORD`).
- `POST /api/auth/login/` returns a token. Send it as `Authorization: Bearer <token>`.
  In Swagger, click **Authorize** and paste the token.
- Tokens are signed and stateless (Django `TimestampSigner`), so no database or session store is needed.
  They expire after 12 hours (`AUTH_TOKEN_MAX_AGE`, in seconds).
- Missing token on a write: `401 {"detail": "Please log in to continue."}`. Expired or invalid token: 401 with a
  message asking to log in again. Wrong credentials: `400 {"detail": "Invalid email or password."}`.

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login/ -H "Content-Type: application/json" \
  -d '{"email":"staff@medslot.app","password":"medslot123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -X POST localhost:8000/api/appointments/ -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{...}'
```

## Clinic rules (enforced by the backend)

1. Open Monday to Saturday, 09:00 to 17:00. The appointment must start at or after 09:00 and end by 17:00.
2. Start times are on a 15-minute boundary (:00, :15, :30, :45). Durations are 15, 30, 45 or 60 minutes (default 30).
3. A doctor can't have overlapping appointments. Booked and completed ones hold their time; only cancelling frees a slot.
4. No booking in the past, including earlier today. Time is local to `Asia/Karachi`.
5. Only a `booked` appointment can become `cancelled` or `completed`. Both are final.
6. `patient_phone` is 10 to 13 digits. `patient_name` is required. `doctor` is 1, 2 or 3.

## Errors

Every 4xx response has a human-readable `detail` string. Field validation errors also include `errors`:

```json
{"detail": "Dr. Ali already has an appointment at 10:30 on 2026-11-10."}
{"detail": "Patient name is required.", "errors": {"patient_name": ["Patient name is required."]}}
{"detail": "Appointment 99 not found."}
```

## What's finished

All core requirements, plus every bonus item:

- [x] Booking, listing, cancelling and completing appointments, with all clinic rules enforced server-side
- [x] Staff login (signed Bearer tokens) for booking and status changes; reads stay public
- [x] Pagination on the appointment list (`page`, `page_size`)
- [x] Search by patient name or phone
- [x] Tests (`python manage.py test`): rules, status changes, filters, pagination, doctor's day, auth
- [x] Doctor's day view (`/api/appointments/doctor-day/`)
- [x] Docker Compose for both apps
- [x] Swagger / OpenAPI docs at `/api/docs/`, validated with `spectacular --validate --fail-on-warn`

## Storage

There is no database, by design. Appointments are kept in a thread-safe, in-memory store
(`appointments/store.py`), so all data is lost when the server restarts. The domain model is
in `appointments/models.py` and the doctors list is in `appointments/doctors.py`.

## Layout

```
appointments/
  doctors.py      fixed doctor list
  models.py       Appointment dataclass and Status choices
  store.py        in-memory, lock-protected store
  services.py     clinic rules and operations
  serializers.py  input validation and response shapes
  views.py        thin API views with OpenAPI docs
  exceptions.py   error types and the consistent error format
  staff.py        staff account (from settings) and signed login tokens
  authentication.py  Bearer token DRF authentication and its Swagger scheme
  tests.py        API tests
Dockerfile, docker-compose.yml   container setup for the API and both apps
```
