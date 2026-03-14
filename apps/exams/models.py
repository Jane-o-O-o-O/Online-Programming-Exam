from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class KnowledgeTag(TimeStampedModel):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self) -> str:
        return self.name


class Question(TimeStampedModel):
    class QuestionType(models.TextChoices):
        SINGLE = "single", "单选题"
        MULTIPLE = "multiple", "多选题"
        PROGRAM = "program", "编程题"

    class Difficulty(models.IntegerChoices):
        EASY = 1, "简单"
        MEDIUM = 2, "中等"
        HARD = 3, "困难"

    title = models.CharField(max_length=200)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    difficulty = models.PositiveSmallIntegerField(choices=Difficulty.choices, default=Difficulty.MEDIUM)
    language = models.CharField(max_length=30, blank=True)
    prompt = models.TextField()
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.JSONField(default=dict, blank=True)
    reference_answer = models.TextField(blank=True)
    tags = models.ManyToManyField(KnowledgeTag, blank=True)

    def __str__(self) -> str:
        return self.title


class Exam(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        FINISHED = "finished", "已结束"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_exams")

    def __str__(self) -> str:
        return self.title


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="exam_questions")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="exam_questions")
    order = models.PositiveIntegerField(default=1)
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        unique_together = ("exam", "question")
        ordering = ("order", "id")


class Submission(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "作答中"
        SUBMITTED = "submitted", "已提交"
        JUDGING = "judging", "判题中"
        COMPLETED = "completed", "已完成"

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    total_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("exam", "student")


class Answer(TimeStampedModel):
    class JudgeStatus(models.TextChoices):
        PENDING = "pending", "待判题"
        ACCEPTED = "accepted", "通过"
        WRONG = "wrong", "错误"
        COMPILE_ERROR = "compile_error", "编译错误"
        RUNTIME_ERROR = "runtime_error", "运行错误"
        TIME_LIMIT = "time_limit", "超时"

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    answer_payload = models.JSONField(default=dict, blank=True)
    source_code = models.TextField(blank=True)
    auto_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    judge_status = models.CharField(max_length=30, choices=JudgeStatus.choices, default=JudgeStatus.PENDING)
    judge_feedback = models.TextField(blank=True)

    class Meta:
        unique_together = ("submission", "question")
