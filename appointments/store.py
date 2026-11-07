"""Thread-safe in-memory storage for appointments (a process-wide singleton)."""

import threading
from dataclasses import replace

from .models import Appointment


class AppointmentStore:
    def __init__(self) -> None:
        # Re-entrant so services can hold the lock across a check-then-write
        # sequence while still calling the store's own (locking) methods.
        self.lock = threading.RLock()
        self._appointments: dict[int, Appointment] = {}
        self._next_id = 1

    def add(self, **fields) -> Appointment:
        with self.lock:
            appointment = Appointment(id=self._next_id, **fields)
            self._appointments[appointment.id] = appointment
            self._next_id += 1
            return appointment

    def get(self, appointment_id: int) -> Appointment | None:
        with self.lock:
            return self._appointments.get(appointment_id)

    def all(self) -> list[Appointment]:
        with self.lock:
            return list(self._appointments.values())

    def update(self, appointment: Appointment, **changes) -> Appointment:
        with self.lock:
            updated = replace(appointment, **changes)
            self._appointments[updated.id] = updated
            return updated

    def reset(self) -> None:
        with self.lock:
            self._appointments.clear()
            self._next_id = 1


store = AppointmentStore()
