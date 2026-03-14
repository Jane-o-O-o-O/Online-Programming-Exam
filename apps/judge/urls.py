from django.urls import path

from .views import queue_status

urlpatterns = [
    path("queue-status/", queue_status, name="judge-queue-status"),
]
