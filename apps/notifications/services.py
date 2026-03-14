import random
import string

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from .models import Notification


def generate_numeric_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def build_password_reset_cache_key(email: str) -> str:
    return f"password-reset-code:{email.lower()}"


def store_password_reset_code(email: str, user_id: int, code: str) -> None:
    payload = {
        "user_id": user_id,
        "code": code,
        "attempts": 0,
        "created_at": timezone.now().isoformat(),
    }
    cache.set(build_password_reset_cache_key(email), payload, timeout=settings.PASSWORD_RESET_CODE_TTL)


def get_password_reset_state(email: str):
    return cache.get(build_password_reset_cache_key(email))


def clear_password_reset_state(email: str) -> None:
    cache.delete(build_password_reset_cache_key(email))


def increment_password_reset_attempts(email: str):
    state = get_password_reset_state(email)
    if not state:
        return None
    state["attempts"] = int(state.get("attempts", 0)) + 1
    cache.set(build_password_reset_cache_key(email), state, timeout=settings.PASSWORD_RESET_CODE_TTL)
    return state


def send_notification_email(*, user, subject: str, body: str, recipient: str, category: str = Notification.Category.EMAIL) -> Notification:
    notification = Notification.objects.create(
        user=user,
        category=category,
        title=subject,
        content=body,
        recipient=recipient,
        status=Notification.Status.PENDING,
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
        notification.error_message = ""
    except Exception as exc:
        notification.status = Notification.Status.FAILED
        notification.error_message = str(exc)
    notification.save(update_fields=["status", "sent_at", "error_message"])
    return notification


def send_password_reset_code(*, user) -> Notification:
    code = generate_numeric_code()
    store_password_reset_code(user.email, user.id, code)
    body = (
        f"您好，{user.username}：\n\n"
        f"您的在线编程考试系统验证码是：{code}\n"
        f"有效期 {settings.PASSWORD_RESET_CODE_TTL // 60} 分钟，请勿泄露给他人。\n\n"
        "如果这不是您的操作，请忽略本邮件。"
    )
    return send_notification_email(
        user=user,
        subject="在线编程考试系统密码重置验证码",
        body=body,
        recipient=user.email,
        category=Notification.Category.SECURITY,
    )
