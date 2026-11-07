"""
Domain model for appointments.

This project has no database by design, so these are not Django ORM models.
An ``Appointment`` is a plain, immutable dataclass held in the in-memory
store (see ``store.py``). Data is lost when the server restarts.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db.models import TextChoices

from .doctors import Doctor, get_doctor

DURATION_CHOICES = (15, 30, 45, 60)
DEFAULT_DURATION = 30


class Status(TextChoices):
    BOOKED = "booked", "Booked"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


@dataclass(frozen=True)
class Appointment:
    id: int
    doctor_id: int
    patient_name: str
    patient_phone: str
    date: date
    start_time: time
    duration_minutes: int
    reason: str
    status: Status
    created_at: datetime

    @property
    def doctor(self) -> Doctor:
        return get_doctor(self.doctor_id)

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.date, self.start_time)

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)

    @property
    def end_time(self) -> time:
        return self.ends_at.time()

    @property
    def is_active(self) -> bool:
        return self.status == Status.BOOKED
