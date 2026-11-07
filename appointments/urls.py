from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("doctors/", views.DoctorListView.as_view(), name="doctor-list"),
    path("appointments/", views.AppointmentListCreateView.as_view(), name="appointment-list"),
    # Must stay above the <int:appointment_id> route.
    path(
        "appointments/available-slots/",
        views.AvailableSlotsView.as_view(),
        name="appointment-available-slots",
    ),
    path(
        "appointments/<int:appointment_id>/",
        views.AppointmentDetailView.as_view(),
        name="appointment-detail",
    ),
]
