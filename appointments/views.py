"""HTTP layer: parse input with serializers, call services, return responses."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services, staff
from .doctors import DOCTORS, get_doctor
from .exceptions import InvalidCredentials
from .models import Status
from .services import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from .serializers import (
    AppointmentFilterSerializer,
    AppointmentPageSerializer,
    AppointmentSerializer,
    AppointmentStatusUpdateSerializer,
    AvailableSlotsQuerySerializer,
    AvailableSlotsSerializer,
    DoctorDaySerializer,
    DoctorSerializer,
    ErrorSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    StaffUserSerializer,
)

DOCTOR_IDS = list(DOCTORS)


def doctor_param(required: bool) -> OpenApiParameter:
    return OpenApiParameter(
        "doctor", OpenApiTypes.INT, required=required, enum=DOCTOR_IDS,
        description="Doctor id (1 Dr. Ali, 2 Dr. Sara, 3 Dr. Usman).",
    )


def date_param(required: bool) -> OpenApiParameter:
    return OpenApiParameter(
        "date", OpenApiTypes.DATE, required=required, description="Date in YYYY-MM-DD format.",
    )


ID_PARAM = OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, description="Appointment id.")


class DoctorListView(APIView):
    @extend_schema(
        tags=["Doctors"],
        summary="List doctors",
        description="The clinic's fixed list of doctors (used for the booking dropdown).",
        responses={200: DoctorSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        return Response(DoctorSerializer(DOCTORS.values(), many=True).data)


class AppointmentListCreateView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]  # Reading is public; booking needs a staff login.

    @extend_schema(
        tags=["Appointments"],
        summary="List appointments",
        operation_id="appointments_list",
        description=(
            "Appointments sorted by date, then start time, one page at a time. Every filter is "
            "optional and applies before paginating. Invalid `page` or `page_size` values return 400; "
            "a page past `total_pages` returns 404."
        ),
        parameters=[
            doctor_param(required=False),
            date_param(required=False),
            OpenApiParameter("status", OpenApiTypes.STR, enum=Status.values, description="Appointment status."),
            OpenApiParameter("search", OpenApiTypes.STR, description="Case-insensitive match on patient name or phone."),
            OpenApiParameter("page", OpenApiTypes.INT, default=1, description="Page number, starting at 1."),
            OpenApiParameter(
                "page_size", OpenApiTypes.INT, default=DEFAULT_PAGE_SIZE,
                description=f"Appointments per page, 1 to {MAX_PAGE_SIZE}.",
            ),
        ],
        responses={200: AppointmentPageSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        examples=[
            OpenApiExample(
                "Page out of range",
                response_only=True,
                status_codes=["404"],
                value={"detail": "Page 5 does not exist."},
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        filters = AppointmentFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        appointments = services.list_appointments(
            doctor_id=params.get("doctor"),
            date=params.get("date"),
            status=params.get("status"),
            search=params["search"],
        )
        page = services.paginate(appointments, page=params["page"], page_size=params["page_size"])
        return Response(AppointmentPageSerializer(page).data)

    @extend_schema(
        tags=["Appointments"],
        summary="Book an appointment",
        description=(
            "Requires a staff login (Bearer token). "
            "Creates a `booked` appointment. Clinic rules: open Monday to Saturday, 09:00 to 17:00; "
            "start on a 15-minute boundary; duration 15, 30, 45 or 60 minutes; not in the past; "
            "no overlap with the doctor's other booked appointments. "
            "`id`, `status`, `end_time` and `created_at` are set by the server."
        ),
        request=AppointmentSerializer,
        responses={201: AppointmentSerializer, 400: ErrorSerializer, 401: ErrorSerializer},
        examples=[
            OpenApiExample(
                "Book a 30-minute appointment",
                request_only=True,
                value={
                    "doctor": 1,
                    "patient_name": "Ayesha Khan",
                    "patient_phone": "03001234567",
                    "date": "2026-11-10",
                    "start_time": "10:30",
                    "duration_minutes": 30,
                    "reason": "Follow-up check",
                },
            ),
            OpenApiExample(
                "Slot already taken",
                response_only=True,
                status_codes=["400"],
                value={"detail": "Dr. Ali already has an appointment at 10:30 on 2026-11-10."},
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = AppointmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.book_appointment(**serializer.validated_data)
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)


class AppointmentDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]  # Reading is public; status changes need a staff login.

    @extend_schema(
        tags=["Appointments"],
        summary="Get an appointment",
        parameters=[ID_PARAM],
        responses={200: AppointmentSerializer, 404: ErrorSerializer},
    )
    def get(self, request: Request, appointment_id: int) -> Response:
        appointment = services.get_appointment(appointment_id)
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        tags=["Appointments"],
        summary="Cancel or complete an appointment",
        description=(
            "Requires a staff login (Bearer token). "
            "Only `status` can change, and only from `booked` to `cancelled` or `completed`. "
            "Completed and cancelled appointments are final. Cancelling frees the slot."
        ),
        parameters=[ID_PARAM],
        request=AppointmentStatusUpdateSerializer,
        responses={
            200: AppointmentSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
        examples=[
            OpenApiExample("Cancel", request_only=True, value={"status": "cancelled"}),
            OpenApiExample("Complete", request_only=True, value={"status": "completed"}),
        ],
    )
    def patch(self, request: Request, appointment_id: int) -> Response:
        serializer = AppointmentStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.change_status(appointment_id, serializer.validated_data["status"])
        return Response(AppointmentSerializer(appointment).data)


class AvailableSlotsView(APIView):
    @extend_schema(
        tags=["Appointments"],
        summary="Available 30-minute slots",
        description=(
            "Free 30-minute start times between 09:00 and 16:30 for one doctor on one date: the "
            "`free` slots of the doctor's day view. Slots overlapping a booked or completed appointment "
            "and slots already in the past are left out, so a past date or a Sunday returns an empty list."
        ),
        parameters=[doctor_param(required=True), date_param(required=True)],
        responses={200: AvailableSlotsSerializer, 400: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        query = AvailableSlotsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        doctor_id, day = query.validated_data["doctor"], query.validated_data["date"]
        slots = services.available_slots(doctor_id, day)
        return Response(
            AvailableSlotsSerializer(
                {
                    "doctor": get_doctor(doctor_id),
                    "date": day,
                    "slots": [slot.strftime("%H:%M") for slot in slots],
                }
            ).data
        )


class DoctorDayView(APIView):
    @extend_schema(
        tags=["Appointments"],
        summary="Doctor's day view",
        description=(
            "Every 30-minute slot from 09:00 to 16:30 for one doctor on one date. A slot is `booked` "
            "when a booked or completed appointment overlaps it (a 60-minute appointment covers two "
            "slots, both referencing it); cancelled appointments leave it free. A free slot that has "
            "already started is `past`. On Sundays `is_open` is false and `slots` is empty."
        ),
        parameters=[doctor_param(required=True), date_param(required=True)],
        responses={200: DoctorDaySerializer, 400: ErrorSerializer},
        examples=[
            OpenApiExample(
                "Day with one booking",
                response_only=True,
                value={
                    "doctor": {"id": 1, "name": "Dr. Ali", "specialty": "Cardiology"},
                    "date": "2026-11-10",
                    "is_open": True,
                    "summary": {"free": 15, "booked": 1, "past": 0},
                    "slots": [
                        {"start": "09:00", "end": "09:30", "status": "free", "appointment": None},
                        {
                            "start": "09:30",
                            "end": "10:00",
                            "status": "booked",
                            "appointment": {
                                "id": 4,
                                "patient_name": "Ayesha Khan",
                                "start_time": "09:30",
                                "end_time": "10:00",
                                "duration_minutes": 30,
                                "status": "booked",
                            },
                        },
                    ],
                },
            ),
        ],
    )
    def get(self, request: Request) -> Response:
        query = AvailableSlotsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        day = services.doctor_day(query.validated_data["doctor"], query.validated_data["date"])
        return Response(DoctorDaySerializer(day).data)


class LoginView(APIView):
    authentication_classes = []  # A stale token must not block logging in again.
    permission_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="Staff login",
        description=(
            "Exchanges staff credentials for a signed token. Send it on writes as "
            "`Authorization: Bearer <token>` (or paste it into Swagger's Authorize button)."
        ),
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 400: ErrorSerializer},
        examples=[
            OpenApiExample(
                "Demo staff account",
                request_only=True,
                value={"email": "staff@medslot.app", "password": "medslot123"},
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = staff.check_credentials(**serializer.validated_data)
        if user is None:
            raise InvalidCredentials()
        return Response(
            LoginResponseSerializer({"token": staff.issue_token(user), "user": user}).data
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Auth"],
        summary="Current staff user",
        description="Returns the logged-in staff member. 401 if the token is missing, invalid or expired.",
        responses={200: StaffUserSerializer, 401: ErrorSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(StaffUserSerializer(request.user).data)
