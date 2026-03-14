from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.exams.models import Exam, ExamQuestion, Question

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo teacher/student users and a published demo exam."

    def handle(self, *args, **options):
        teacher, _ = User.objects.get_or_create(
            username="demo_teacher",
            defaults={
                "email": "demo_teacher@example.com",
                "role": User.Role.TEACHER,
                "real_name": "Demo Teacher",
            },
        )
        teacher.set_password("Demo123456")
        teacher.save(update_fields=["password"])

        student, _ = User.objects.get_or_create(
            username="demo_student",
            defaults={
                "email": "demo_student@example.com",
                "role": User.Role.STUDENT,
                "real_name": "Demo Student",
            },
        )
        student.set_password("Demo123456")
        student.save(update_fields=["password"])

        single_question, _ = Question.objects.get_or_create(
            title="Python 基础单选",
            defaults={
                "question_type": Question.QuestionType.SINGLE,
                "prompt": "Python 列表推导式返回的是什么类型？",
                "options": ["tuple", "list", "dict", "set"],
                "correct_answer": {"value": "list"},
            },
        )

        program_question, _ = Question.objects.get_or_create(
            title="两数求和",
            defaults={
                "question_type": Question.QuestionType.PROGRAM,
                "language": "python",
                "prompt": "读取一行中的两个整数，输出它们的和。",
                "reference_answer": "a, b = map(int, input().split())\nprint(a + b)",
                "correct_answer": {
                    "cases": [
                        {"input": "1 2\n", "output": "3\n"},
                        {"input": "100 250\n", "output": "350\n"},
                    ],
                    "time_limit_seconds": 2,
                },
            },
        )

        now = timezone.now()
        exam, created = Exam.objects.get_or_create(
            title="系统演示考试",
            defaults={
                "description": "包含客观题和编程题的演示考试",
                "starts_at": now - timedelta(hours=1),
                "ends_at": now + timedelta(days=7),
                "duration_minutes": 90,
                "status": Exam.Status.PUBLISHED,
                "created_by": teacher,
            },
        )
        if created:
            ExamQuestion.objects.create(exam=exam, question=single_question, order=1, score=20)
            ExamQuestion.objects.create(exam=exam, question=program_question, order=2, score=80)

        self.stdout.write(self.style.SUCCESS("Demo data ready"))
        self.stdout.write("teacher: demo_teacher / Demo123456")
        self.stdout.write("student: demo_student / Demo123456")
        self.stdout.write(f"exam_id: {exam.id}")
