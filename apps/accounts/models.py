from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        TEACHER = "teacher", "教师"
        STUDENT = "student", "学生"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    real_name = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=20, blank=True)

    def __str__(self) -> str:
        return self.username
