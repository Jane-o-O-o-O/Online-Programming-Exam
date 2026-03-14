from django.urls import path

from .views import queue_status, retry_task, task_list

urlpatterns = [
    path("queue-status/", queue_status, name="judge-queue-status"),
    path("tasks/", task_list, name="judge-task-list"),
    path("tasks/<int:task_id>/retry/", retry_task, name="judge-task-retry"),
]
