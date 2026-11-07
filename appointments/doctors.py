"""The clinic's doctors. A fixed list in code: there is no database."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Doctor:
    id: int
    name: str
    specialty: str


DOCTORS: dict[int, Doctor] = {
    doctor.id: doctor
    for doctor in (
        Doctor(id=1, name="Dr. Ali", specialty="Cardiology"),
        Doctor(id=2, name="Dr. Sara", specialty="General Medicine"),
        Doctor(id=3, name="Dr. Usman", specialty="Pediatrics"),
    )
}

DOCTOR_CHOICES = [(doctor.id, doctor.name) for doctor in DOCTORS.values()]


def get_doctor(doctor_id: int) -> Doctor:
    return DOCTORS[doctor_id]
