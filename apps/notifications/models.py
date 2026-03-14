from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    class Category(models.TextChoices):
        EMAIL = "email", "邮件"
        SYSTEM = "system", "系统"
        EXAM = "exam", "考试"
        SECURITY = "security", "安全"

    class Status(models.TextChoices):
        PENDING = "pending", "待发送"
        SENT = "sent", "已发送"
        FAILED = "failed", "发送失败"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    title = models.CharField(max_length=100)
    content = models.TextField()
    recipient = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_read(self) -> None:
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])

    def __str__(self) -> str:
        return self.title
