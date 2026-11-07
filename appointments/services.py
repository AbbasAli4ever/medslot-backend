"""Clinic rules and appointment operations. Views stay thin and call these."""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .exceptions import AppointmentNotFound, BookingRuleError, PageNotFound
from .models import Appointment, Status
from .store import store

OPENING_TIME = time(9, 0)
CLOSING_TIME = time(17, 0)
SLOT_BOUNDARY_MINUTES = 15
SLOT_LENGTH_MINUTES = 30
SUNDAY = 6
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


def now() -> datetime:
    """Current local time in the clinic's zone (settings.TIME_ZONE). Patched in tests."""
    return timezone.localtime()


def _local_now() -> datetime:
    """``now()`` as a naive wall-clock datetime, comparable with appointment times."""
    return timezone.localtime(now()).replace(tzinfo=None)


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """True if the intervals [start_a, end_a) and [start_b, end_b) intersect."""
    return start_a < end_b and start_b < end_a


def _active_appointments(doctor_id: int, day: date) -> list[Appointment]:
    return [
        a for a in store.all()
        if a.doctor_id == doctor_id and a.date == day and a.is_active
    ]


def _check_clinic_hours(day: date, start_time: time, duration_minutes: int) -> None:
    starts_at = datetime.combine(day, start_time)
    ends_at = starts_at + timedelta(minutes=duration_minutes)

    if starts_at < _local_now():
        raise BookingRuleError("Appointments cannot be booked in the past.")
    if day.weekday() == SUNDAY:
        raise BookingRuleError("The clinic is closed on Sundays.")
    if start_time < OPENING_TIME or ends_at > datetime.combine(day, CLOSING_TIME):
        raise BookingRuleError("Appointments must be between 09:00 and 17:00.")
    if start_time.minute % SLOT_BOUNDARY_MINUTES or start_time.second:
        raise BookingRuleError(
            "Start time must be on a 15-minute boundary (:00, :15, :30 or :45)."
        )


def _check_doctor_is_free(doctor_id: int, day: date, start_time: time, duration_minutes: int) -> None:
    starts_at = datetime.combine(day, start_time)
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    for existing in _active_appointments(doctor_id, day):
        if _overlaps(starts_at, ends_at, existing.starts_at, existing.ends_at):
            raise BookingRuleError(
                f"{existing.doctor.name} already has an appointment at "
                f"{existing.start_time:%H:%M} on {day.isoformat()}."
            )


def book_appointment(
    *,
    doctor_id: int,
    patient_name: str,
    patient_phone: str,
    date: date,
    start_time: time,
    duration_minutes: int,
    reason: str = "",
) -> Appointment:
    _check_clinic_hours(date, start_time, duration_minutes)
    # Hold the lock across check-and-insert so two requests can't take the same slot.
    with store.lock:
        _check_doctor_is_free(doctor_id, date, start_time, duration_minutes)
        return store.add(
            doctor_id=doctor_id,
            patient_name=patient_name,
            patient_phone=patient_phone,
            date=date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            reason=reason,
            status=Status.BOOKED,
            created_at=now(),
        )


def get_appointment(appointment_id: int) -> Appointment:
    appointment = store.get(appointment_id)
    if appointment is None:
        raise AppointmentNotFound(appointment_id)
    return appointment


def change_status(appointment_id: int, new_status: Status) -> Appointment:
    """Only a booked appointment can become cancelled or completed; final states are locked."""
    with store.lock:
        appointment = get_appointment(appointment_id)
        if not appointment.is_active:
            raise BookingRuleError(
                f"This appointment is already {appointment.status} and cannot be changed."
            )
        return store.update(appointment, status=Status(new_status))


def list_appointments(
    *,
    doctor_id: int | None = None,
    date: date | None = None,
    status: str | None = None,
    search: str = "",
) -> list[Appointment]:
    appointments = store.all()
    if doctor_id is not None:
        appointments = [a for a in appointments if a.doctor_id == doctor_id]
    if date is not None:
        appointments = [a for a in appointments if a.date == date]
    if status:
        appointments = [a for a in appointments if a.status == status]
    if search:
        term = search.strip().lower()
        appointments = [
            a for a in appointments
            if term in a.patient_name.lower() or term in a.patient_phone
        ]
    return sorted(appointments, key=lambda a: (a.date, a.start_time, a.id))


@dataclass(frozen=True)
class Page:
    count: int
    page: int
    page_size: int
    total_pages: int
    results: list


def paginate(items: list, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> Page:
    """Slice ``items`` into one page. An empty list is still page 1 of 1."""
    count = len(items)
    total_pages = max(1, math.ceil(count / page_size))
    if page > total_pages:
        raise PageNotFound(page)
    offset = (page - 1) * page_size
    return Page(
        count=count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        results=items[offset:offset + page_size],
    )


def available_slots(doctor_id: int, day: date) -> list[time]:
    """Free 30-minute slots (09:00 to 16:30) for a doctor, excluding any in the past."""
    if day.weekday() == SUNDAY:
        return []

    booked = _active_appointments(doctor_id, day)
    current = _local_now()
    slot_length = timedelta(minutes=SLOT_LENGTH_MINUTES)
    slot_start = datetime.combine(day, OPENING_TIME)
    closing = datetime.combine(day, CLOSING_TIME)

    slots = []
    while slot_start + slot_length <= closing:
        slot_end = slot_start + slot_length
        is_free = not any(_overlaps(slot_start, slot_end, a.starts_at, a.ends_at) for a in booked)
        if slot_start >= current and is_free:
            slots.append(slot_start.time())
        slot_start = slot_end
    return slots
