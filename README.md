# Clinic Appointment Booker: API

Django REST Framework backend for booking, listing, cancelling and completing clinic appointments.

The Next.js frontend lives in a separate repo: https://github.com/AbbasAli4ever/medslot-frontend

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
| GET | `/api/appointments/` | List, sorted by date then start time. Filters: `doctor`, `date`, `status`, `search` (patient name or phone) |
| POST | `/api/appointments/` | Book an appointment (201). **Staff login required** |
| GET | `/api/appointments/{id}/` | One appointment (404 if missing) |
| PATCH | `/api/appointments/{id}/` | `{"status": "cancelled"}` or `{"status": "completed"}`. **Staff login required** |
| GET | `/api/appointments/available-slots/?doctor=1&date=YYYY-MM-DD` | Free 30-minute slots, 09:00 to 16:30 |

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
3. A doctor can't have overlapping `booked` appointments. Cancelled and completed ones don't block a slot.
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
```
