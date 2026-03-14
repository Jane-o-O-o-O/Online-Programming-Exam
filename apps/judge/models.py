from django.db import models

from apps.exams.models import Answer


class JudgeTask(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "执行中"
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    answer = models.OneToOneField(Answer, on_delete=models.CASCADE, related_name="judge_task")
    language = models.CharField(max_length=30)
    docker_image = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    result_payload = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"JudgeTask<{self.answer_id}>"
