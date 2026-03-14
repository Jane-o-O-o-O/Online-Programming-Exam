from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def home(_request):
    return JsonResponse(
        {
            "project": "online-exam-system",
            "status": "running",
            "modules": ["accounts", "exams", "judge", "notifications"],
        }
    )


urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/exams/", include("apps.exams.urls")),
    path("api/judge/", include("apps.judge.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
]
