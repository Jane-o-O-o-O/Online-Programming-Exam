from celery import shared_task

from django.contrib.auth import get_user_model

from .services import send_password_reset_code

User = get_user_model()


@shared_task
def send_password_reset_code_task(user_id: int) -> int:
    user = User.objects.get(pk=user_id)
    notification = send_password_reset_code(user=user)
    return notification.id
