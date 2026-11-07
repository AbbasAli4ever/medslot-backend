from django.urls import include, path
from drf_spectacular.utils import extend_schema, inline_serializer
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response


@extend_schema(
    summary="Health check",
    tags=["health"],
    responses=inline_serializer(
        name="HealthResponse",
        fields={"status": serializers.CharField()},
    ),
)
@api_view(["GET"])
def health(request: Request) -> Response:
    return Response({"status": "ok"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include("appointments.urls")),
]
