import time as clock
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .store import store

LIST_URL = "/api/appointments/"
SLOTS_URL = "/api/appointments/available-slots/"
LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/auth/me/"


def staff_login(client: APIClient, password: str | None = None):
    return client.post(
        LOGIN_URL,
        {"email": settings.STAFF_EMAIL, "password": password or settings.STAFF_PASSWORD},
        format="json",
    )


def next_weekday(weekday: int):
    """The next date (strictly after today) falling on ``weekday`` (Monday is 0)."""
    today = timezone.localdate()
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


class AppointmentAPITestCase(SimpleTestCase):
    def setUp(self):
        store.reset()
        self.client = APIClient()
        token = staff_login(self.client).data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.monday = next_weekday(0)
        self.day = self.monday.isoformat()

    def payload(self, **overrides):
        data = {
            "doctor": 1,
            "patient_name": "Ayesha Khan",
            "patient_phone": "03001234567",
            "date": self.day,
            "start_time": "10:30",
            "duration_minutes": 30,
            "reason": "Checkup",
        }
        data.update(overrides)
        return data

    def book(self, **overrides):
        return self.client.post(LIST_URL, self.payload(**overrides), format="json")

    def assert_rule_error(self, response, message):
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data, {"detail": message})

    def freeze_now(self, day, at: time):
        moment = timezone.make_aware(datetime.combine(day, at))
        patcher = patch("appointments.services.now", return_value=moment)
        patcher.start()
        self.addCleanup(patcher.stop)


class BookingTests(AppointmentAPITestCase):
    def test_successful_booking(self):
        response = self.book()

        self.assertEqual(response.status_code, 201)
        body = response.data
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["doctor"], 1)
        self.assertEqual(
            body["doctor_detail"], {"id": 1, "name": "Dr. Ali", "specialty": "Cardiology"}
        )
        self.assertEqual(body["date"], self.day)
        self.assertEqual(body["start_time"], "10:30")
        self.assertEqual(body["end_time"], "11:00")
        self.assertEqual(body["status"], "booked")
        self.assertEqual(body["reason"], "Checkup")
        self.assertIn("created_at", body)

    def test_defaults_and_ignores_server_controlled_fields(self):
        data = self.payload(status="cancelled", id=99, end_time="16:00")
        del data["duration_minutes"], data["reason"]

        body = self.client.post(LIST_URL, data, format="json").data

        self.assertEqual(body["duration_minutes"], 30)
        self.assertEqual(body["reason"], "")
        self.assertEqual(body["status"], "booked")
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["end_time"], "11:00")

    def test_double_booking_same_slot(self):
        self.book()
        response = self.book(patient_name="Someone Else")
        self.assert_rule_error(
            response, f"Dr. Ali already has an appointment at 10:30 on {self.day}."
        )

    def test_partial_overlap_rejected_but_other_doctor_ok(self):
        self.book(start_time="10:00", duration_minutes=60)

        response = self.book(start_time="10:30")
        self.assert_rule_error(
            response, f"Dr. Ali already has an appointment at 10:00 on {self.day}."
        )
        self.assertEqual(self.book(start_time="10:30", doctor=2).status_code, 201)

    def test_back_to_back_appointments_are_allowed(self):
        self.book(start_time="10:00", duration_minutes=30)
        self.assertEqual(self.book(start_time="10:30").status_code, 201)

    def test_past_date_rejected(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        response = self.book(date=yesterday.isoformat())
        self.assert_rule_error(response, "Appointments cannot be booked in the past.")

    def test_earlier_today_rejected(self):
        self.freeze_now(self.monday, time(12, 0))
        self.assert_rule_error(
            self.book(start_time="11:45"), "Appointments cannot be booked in the past."
        )
        self.assertEqual(self.book(start_time="12:00").status_code, 201)

    def test_sunday_rejected(self):
        response = self.book(date=next_weekday(6).isoformat())
        self.assert_rule_error(response, "The clinic is closed on Sundays.")

    def test_outside_opening_hours_rejected(self):
        message = "Appointments must be between 09:00 and 17:00."
        self.assert_rule_error(self.book(start_time="08:45"), message)
        self.assert_rule_error(self.book(start_time="16:45", duration_minutes=30), message)
        self.assertEqual(self.book(start_time="16:00", duration_minutes=60).status_code, 201)

    def test_start_time_must_be_on_15_minute_boundary(self):
        self.assert_rule_error(
            self.book(start_time="10:10"),
            "Start time must be on a 15-minute boundary (:00, :15, :30 or :45).",
        )

    def test_invalid_phone_rejected(self):
        for phone in ("03001abc567", "123456789", "12345678901234"):
            with self.subTest(phone=phone):
                response = self.book(patient_phone=phone)
                self.assertEqual(response.status_code, 400)
                self.assertIn("patient_phone", response.data["errors"])
                self.assertEqual(response.data["detail"], response.data["errors"]["patient_phone"][0])

    def test_blank_name_rejected(self):
        response = self.book(patient_name="   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Patient name is required.")
        self.assertIn("patient_name", response.data["errors"])

    def test_invalid_doctor_and_duration_rejected(self):
        response = self.book(doctor=9)
        self.assertEqual(response.status_code, 400)
        self.assertIn("doctor", response.data["errors"])

        response = self.book(duration_minutes=20)
        self.assertEqual(response.status_code, 400)
        self.assertIn("duration_minutes", response.data["errors"])


class StatusChangeTests(AppointmentAPITestCase):
    def setUp(self):
        super().setUp()
        self.appointment_id = self.book().data["id"]
        self.url = f"{LIST_URL}{self.appointment_id}/"

    def patch_status(self, value, url=None):
        return self.client.patch(url or self.url, {"status": value}, format="json")

    def test_cancel_frees_the_slot(self):
        response = self.patch_status("cancelled")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

        slots = self.client.get(SLOTS_URL, {"doctor": 1, "date": self.day}).data["slots"]
        self.assertIn("10:30", slots)
        self.assertEqual(self.book().status_code, 201)

    def test_final_states_cannot_change(self):
        self.assertEqual(self.patch_status("completed").status_code, 200)
        self.assert_rule_error(
            self.patch_status("cancelled"),
            "This appointment is already completed and cannot be changed.",
        )

        other_url = f"{LIST_URL}{self.book(start_time='11:00').data['id']}/"
        self.patch_status("cancelled", other_url)
        self.assert_rule_error(
            self.patch_status("completed", other_url),
            "This appointment is already cancelled and cannot be changed.",
        )

    def test_invalid_status_value_rejected(self):
        for value in ("booked", "deleted", ""):
            with self.subTest(value=value):
                response = self.patch_status(value)
                self.assertEqual(response.status_code, 400)
                self.assertIn("status", response.data["errors"])

    def test_other_fields_cannot_be_patched(self):
        response = self.client.patch(
            self.url, {"status": "cancelled", "patient_name": "X"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("patient_name", response.data["errors"])
        self.assertEqual(self.client.get(self.url).data["status"], "booked")

    def test_missing_appointment_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

        response = self.client.get(f"{LIST_URL}99/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"detail": "Appointment 99 not found."})

        response = self.patch_status("cancelled", f"{LIST_URL}99/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"detail": "Appointment 99 not found."})


class ListTests(AppointmentAPITestCase):
    def setUp(self):
        super().setUp()
        tuesday = (self.monday + timedelta(days=1)).isoformat()
        self.book(start_time="14:00", patient_name="Bilal Ahmed", patient_phone="03111111111")
        self.book(start_time="09:00", doctor=2, patient_name="Ayesha Khan")
        self.book(date=tuesday, start_time="09:00", patient_name="Zara Malik")
        self.client.patch(f"{LIST_URL}3/", {"status": "cancelled"}, format="json")

    def ids(self, **params):
        response = self.client.get(LIST_URL, params)
        self.assertEqual(response.status_code, 200)
        return [a["id"] for a in response.data]

    def test_sorted_by_date_then_start_time(self):
        self.assertEqual(self.ids(), [2, 1, 3])

    def test_filters(self):
        self.assertEqual(self.ids(doctor=1), [1, 3])
        self.assertEqual(self.ids(date=self.day), [2, 1])
        self.assertEqual(self.ids(status="cancelled"), [3])
        self.assertEqual(self.ids(search="bilal"), [1])
        self.assertEqual(self.ids(search="0311"), [1])

    def test_invalid_filters_rejected(self):
        for params in ({"doctor": 9}, {"doctor": "abc"}, {"date": "10-11-2026"}, {"status": "lost"}):
            with self.subTest(params=params):
                response = self.client.get(LIST_URL, params)
                self.assertEqual(response.status_code, 400)
                self.assertIn(next(iter(params)), response.data["errors"])


class DoctorAndSlotTests(AppointmentAPITestCase):
    def test_doctor_list(self):
        response = self.client.get("/api/doctors/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([d["name"] for d in response.data], ["Dr. Ali", "Dr. Sara", "Dr. Usman"])

    def test_slots_exclude_booked_times(self):
        self.book(start_time="10:15", duration_minutes=30)  # covers 10:00 and 10:30 slots

        response = self.client.get(SLOTS_URL, {"doctor": 1, "date": self.day})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["doctor"]["name"], "Dr. Ali")
        self.assertEqual(response.data["date"], self.day)
        slots = response.data["slots"]
        self.assertEqual(slots[0], "09:00")
        self.assertEqual(slots[-1], "16:30")
        self.assertNotIn("10:00", slots)
        self.assertNotIn("10:30", slots)
        self.assertEqual(len(slots), 14)

    def test_slots_exclude_past_times_today(self):
        self.freeze_now(self.monday, time(12, 10))
        slots = self.client.get(SLOTS_URL, {"doctor": 1, "date": self.day}).data["slots"]
        self.assertEqual(slots[0], "12:30")

    def test_slots_empty_on_sunday_and_past_dates(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        for day in (next_weekday(6), yesterday):
            with self.subTest(day=day):
                response = self.client.get(SLOTS_URL, {"doctor": 1, "date": day.isoformat()})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["slots"], [])

    def test_slots_require_valid_params(self):
        for params in ({}, {"doctor": 1}, {"date": self.day}, {"doctor": 9, "date": self.day},
                       {"doctor": 1, "date": "tomorrow"}):
            with self.subTest(params=params):
                response = self.client.get(SLOTS_URL, params)
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.data["detail"], str)


class AuthTests(AppointmentAPITestCase):
    def setUp(self):
        super().setUp()
        self.anonymous = APIClient()

    def me(self, token=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.anonymous.get(ME_URL, **headers)

    def test_login_success(self):
        response = staff_login(self.anonymous)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["token"])
        self.assertEqual(
            response.data["user"], {"email": settings.STAFF_EMAIL, "name": "Front Desk"}
        )

    def test_login_wrong_password(self):
        response = staff_login(self.anonymous, password="wrong-password")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"detail": "Invalid email or password."})

    def test_login_missing_fields(self):
        response = self.anonymous.post(LOGIN_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data["errors"]), {"email", "password"})

    def test_me_with_valid_token(self):
        token = staff_login(self.anonymous).data["token"]
        response = self.me(token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"email": settings.STAFF_EMAIL, "name": "Front Desk"})

    def test_me_without_or_with_bad_token(self):
        response = self.me()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"detail": "Please log in to continue."})

        response = self.me("not-a-real-token")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"detail": "Invalid token. Please log in again."})

    def test_me_with_expired_token(self):
        issued_long_ago = clock.time() - settings.AUTH_TOKEN_MAX_AGE - 60
        with patch("django.core.signing.time.time", return_value=issued_long_ago):
            token = staff_login(self.anonymous).data["token"]

        response = self.me(token)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data, {"detail": "Your session has expired. Please log in again."}
        )

    def test_writes_require_login(self):
        appointment_id = self.book().data["id"]

        response = self.anonymous.post(LIST_URL, self.payload(start_time="11:00"), format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data, {"detail": "Please log in to continue."})

        response = self.anonymous.patch(
            f"{LIST_URL}{appointment_id}/", {"status": "cancelled"}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get(f"{LIST_URL}{appointment_id}/").data["status"], "booked")

    def test_reads_stay_public(self):
        appointment_id = self.book().data["id"]
        for url, params in (
            ("/api/doctors/", {}),
            (LIST_URL, {}),
            (f"{LIST_URL}{appointment_id}/", {}),
            (SLOTS_URL, {"doctor": 1, "date": self.day}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.anonymous.get(url, params).status_code, 200)
