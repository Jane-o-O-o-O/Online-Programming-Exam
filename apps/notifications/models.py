from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        EMAIL = "email", "邮件"
        SYSTEM = "system", "系统"
        EXAM = "exam", "考试"

    class Status(models.TextChoices):
        PENDING = "pending", "待发送"
        SENT = "sent", "已发送"
        FAILED = "failed", "发送失败"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SYSTEM)
    title = models.CharField(max_length=100)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title
