"""Request validation and response shapes for the appointments API."""

from django.core.validators import RegexValidator
from rest_framework import serializers

from .doctors import DOCTOR_CHOICES
from .models import DEFAULT_DURATION, DURATION_CHOICES, SlotStatus, Status
from .services import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

TIME_FORMAT = "%H:%M"
DATE_FORMAT = "%Y-%m-%d"

DOCTOR_ERRORS = {"invalid_choice": "Unknown doctor. Choose one of: 1, 2, 3."}
DATE_ERRORS = {"invalid": "Date must be in YYYY-MM-DD format."}


class DoctorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    specialty = serializers.CharField()


class AppointmentSerializer(serializers.Serializer):
    """Booking input and the full appointment output."""

    id = serializers.IntegerField(read_only=True)
    doctor = serializers.ChoiceField(
        source="doctor_id", choices=DOCTOR_CHOICES, error_messages=DOCTOR_ERRORS
    )
    doctor_detail = DoctorSerializer(source="doctor", read_only=True)
    patient_name = serializers.CharField(
        max_length=100,
        error_messages={
            "required": "Patient name is required.",
            "blank": "Patient name is required.",
        },
    )
    patient_phone = serializers.CharField(
        validators=[
            RegexValidator(
                r"^\d{10,13}$",
                "Phone number must contain digits only and be 10 to 13 characters long.",
            )
        ],
        error_messages={
            "required": "Phone number is required.",
            "blank": "Phone number is required.",
        },
    )
    date = serializers.DateField(
        format=DATE_FORMAT, input_formats=[DATE_FORMAT], error_messages=DATE_ERRORS
    )
    start_time = serializers.TimeField(
        format=TIME_FORMAT,
        input_formats=[TIME_FORMAT],
        error_messages={"invalid": "Start time must be in HH:MM format."},
    )
    duration_minutes = serializers.ChoiceField(
        choices=DURATION_CHOICES,
        default=DEFAULT_DURATION,
        error_messages={"invalid_choice": "Duration must be 15, 30, 45 or 60 minutes."},
    )
    end_time = serializers.TimeField(format=TIME_FORMAT, read_only=True)
    reason = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(choices=Status.choices, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class AppointmentStatusUpdateSerializer(serializers.Serializer):
    """PATCH body: only ``status`` may change, and only to cancelled or completed."""

    status = serializers.ChoiceField(
        choices=[Status.CANCELLED, Status.COMPLETED],
        error_messages={
            "invalid_choice": 'Status can only be changed to "cancelled" or "completed".'
        },
    )

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: ["Only the status of an appointment can be changed."] for field in unknown}
            )
        return attrs


class AppointmentFilterSerializer(serializers.Serializer):
    """Optional query filters and pagination for the appointment list."""

    doctor = serializers.ChoiceField(
        choices=DOCTOR_CHOICES, required=False, error_messages=DOCTOR_ERRORS
    )
    date = serializers.DateField(
        input_formats=[DATE_FORMAT], required=False, error_messages=DATE_ERRORS
    )
    status = serializers.ChoiceField(
        choices=Status.choices,
        required=False,
        error_messages={"invalid_choice": "Status must be booked, completed or cancelled."},
    )
    search = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.IntegerField(
        min_value=1,
        default=1,
        error_messages={
            "invalid": "Page must be a whole number.",
            "min_value": "Page must be 1 or more.",
        },
    )
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=MAX_PAGE_SIZE,
        default=DEFAULT_PAGE_SIZE,
        error_messages={
            "invalid": "Page size must be a whole number.",
            "min_value": f"Page size must be between 1 and {MAX_PAGE_SIZE}.",
            "max_value": f"Page size must be between 1 and {MAX_PAGE_SIZE}.",
        },
    )


class AppointmentPageSerializer(serializers.Serializer):
    """One page of the appointment list."""

    count = serializers.IntegerField(help_text="Appointments matching the filters, across all pages.")
    page = serializers.IntegerField(help_text="This page's number (1-based).")
    page_size = serializers.IntegerField(help_text="Maximum appointments per page.")
    total_pages = serializers.IntegerField(help_text="Number of pages; at least 1, even when count is 0.")
    results = AppointmentSerializer(many=True)


class AvailableSlotsQuerySerializer(serializers.Serializer):
    """Required ``doctor`` and ``date`` query params (available slots and the doctor's day)."""

    doctor = serializers.ChoiceField(
        choices=DOCTOR_CHOICES,
        error_messages={**DOCTOR_ERRORS, "required": "The doctor query parameter is required."},
    )
    date = serializers.DateField(
        input_formats=[DATE_FORMAT],
        error_messages={**DATE_ERRORS, "required": "The date query parameter is required."},
    )


class AvailableSlotsSerializer(serializers.Serializer):
    doctor = DoctorSerializer()
    date = serializers.DateField(format=DATE_FORMAT)
    slots = serializers.ListField(child=serializers.CharField(), help_text="Free start times, HH:MM.")


class DaySlotAppointmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    patient_name = serializers.CharField()
    start_time = serializers.TimeField(format=TIME_FORMAT)
    end_time = serializers.TimeField(format=TIME_FORMAT)
    duration_minutes = serializers.IntegerField()
    status = serializers.ChoiceField(choices=[Status.BOOKED, Status.COMPLETED])


class DaySlotSerializer(serializers.Serializer):
    start = serializers.TimeField(format=TIME_FORMAT, help_text="Slot start, HH:MM.")
    end = serializers.TimeField(format=TIME_FORMAT, help_text="Slot end, HH:MM.")
    status = serializers.ChoiceField(
        choices=SlotStatus.choices,
        help_text="`booked` if a booked or completed appointment overlaps it; `past` if free but already started.",
    )
    appointment = DaySlotAppointmentSerializer(
        allow_null=True, help_text="The appointment occupying this slot, or null."
    )


class DaySummarySerializer(serializers.Serializer):
    free = serializers.IntegerField()
    booked = serializers.IntegerField()
    past = serializers.IntegerField()


class DoctorDaySerializer(serializers.Serializer):
    doctor = DoctorSerializer()
    date = serializers.DateField(format=DATE_FORMAT)
    is_open = serializers.BooleanField(help_text="False on Sundays, when `slots` is empty.")
    summary = DaySummarySerializer()
    slots = DaySlotSerializer(many=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(error_messages={"required": "Email is required.", "blank": "Email is required."})
    password = serializers.CharField(
        trim_whitespace=False,
        style={"input_type": "password"},
        error_messages={"required": "Password is required.", "blank": "Password is required."},
    )


class StaffUserSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField()


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Send as `Authorization: Bearer <token>`. Valid for 12 hours by default.")
    user = StaffUserSerializer()


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField(help_text="Human-readable message, safe to show to users.")
    errors = serializers.DictField(
        child=serializers.ListField(child=serializers.CharField()),
        required=False,
        help_text="Per-field validation messages (validation errors only).",
    )
