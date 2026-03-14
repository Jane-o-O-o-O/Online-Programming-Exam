from django.urls import path

from .views import mark_all_read, mark_read, notifications, summary

urlpatterns = [
    path("summary/", summary, name="notification-summary"),
    path("", notifications, name="notification-list"),
    path("read-all/", mark_all_read, name="notification-read-all"),
    path("<int:notification_id>/read/", mark_read, name="notification-read"),
]
