from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from apps.accounts.models import User
from apps.exams.models import Answer, Exam, ExamQuestion, Question, Submission

from .models import JudgeTask
from .services import get_or_create_judge_task, judge_answer, judge_program_answer


@override_settings(JUDGE_EXECUTION_MODE="local", JUDGE_TIMEOUT_SECONDS=1)
class LocalJudgeTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher_judge", password="pass1234", role="teacher", email="teacher_judge@example.com")
        self.student = User.objects.create_user(username="student_judge", password="pass1234", role="student", email="student_judge@example.com")
        self.question = Question.objects.create(
            title="Sum",
            question_type=Question.QuestionType.PROGRAM,
            language="python",
            prompt="Read two ints and print sum",
            correct_answer={
                "cases": [
                    {"input": "1 2\n", "output": "3\n"},
                    {"input": "10 20\n", "output": "30\n"},
                ],
                "time_limit_seconds": 1,
            },
        )
        self.exam = Exam.objects.create(
            title="Judge Demo",
            description="",
            starts_at="2026-01-01T00:00:00+08:00",
            ends_at="2026-12-31T23:59:59+08:00",
            duration_minutes=120,
            status=Exam.Status.PUBLISHED,
            created_by=self.teacher,
        )
        self.exam_question = ExamQuestion.objects.create(exam=self.exam, question=self.question, score=Decimal("100"), order=1)
        self.submission = Submission.objects.create(exam=self.exam, student=self.student)

    def test_local_judge_accepts_correct_python_solution(self):
        answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            source_code="a, b = map(int, input().split())\nprint(a + b)",
        )

        score = judge_program_answer(answer, self.exam_question)
        answer.refresh_from_db()

        self.assertEqual(score, Decimal("100"))
        self.assertEqual(answer.judge_status, Answer.JudgeStatus.ACCEPTED)
        self.assertEqual(JudgeTask.objects.get(answer=answer).status, JudgeTask.Status.SUCCESS)

    def test_local_judge_marks_wrong_answer(self):
        answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            source_code="a, b = map(int, input().split())\nprint(a - b)",
        )

        score = judge_program_answer(answer, self.exam_question)
        answer.refresh_from_db()

        self.assertEqual(score, Decimal("0"))
        self.assertEqual(answer.judge_status, Answer.JudgeStatus.WRONG)
        self.assertEqual(JudgeTask.objects.get(answer=answer).status, JudgeTask.Status.FAILED)

    def test_teacher_can_retry_failed_local_judge_task(self):
        answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            source_code="a, b = map(int, input().split())\nprint(a - b)",
        )
        judge_program_answer(answer, self.exam_question)
        answer.source_code = "a, b = map(int, input().split())\nprint(a + b)"
        answer.save(update_fields=["source_code"])
        task = JudgeTask.objects.get(answer=answer)

        self.client.force_login(self.teacher)
        response = self.client.post(f"/api/judge/tasks/{task.id}/retry/", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        answer.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(answer.judge_status, Answer.JudgeStatus.ACCEPTED)
        self.assertEqual(task.status, JudgeTask.Status.SUCCESS)

    def test_teacher_can_list_judge_tasks(self):
        answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            source_code="a, b = map(int, input().split())\nprint(a + b)",
        )
        judge_program_answer(answer, self.exam_question)

        self.client.force_login(self.teacher)
        response = self.client.get("/api/judge/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 1)


@override_settings(JUDGE_EXECUTION_MODE="celery", CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class AsyncJudgeTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher_async", password="pass1234", role="teacher", email="teacher_async@example.com")
        self.student = User.objects.create_user(username="student_async", password="pass1234", role="student", email="student_async@example.com")
        self.question = Question.objects.create(
            title="Async Sum",
            question_type=Question.QuestionType.PROGRAM,
            language="python",
            prompt="Read two ints and print sum",
            correct_answer={"cases": [{"input": "2 3\n", "output": "5\n"}], "time_limit_seconds": 1},
        )
        self.exam = Exam.objects.create(
            title="Async Judge Demo",
            description="",
            starts_at="2026-01-01T00:00:00+08:00",
            ends_at="2026-12-31T23:59:59+08:00",
            duration_minutes=120,
            status=Exam.Status.PUBLISHED,
            created_by=self.teacher,
        )
        self.exam_question = ExamQuestion.objects.create(exam=self.exam, question=self.question, score=Decimal("100"), order=1)
        self.submission = Submission.objects.create(exam=self.exam, student=self.student, status=Submission.Status.JUDGING, submitted_at=timezone.now())

    def test_async_judge_eager_mode_updates_submission_score(self):
        answer = Answer.objects.create(
            submission=self.submission,
            question=self.question,
            source_code="a, b = map(int, input().split())\nprint(a + b)",
        )

        score = judge_answer(answer, self.exam_question)
        answer.refresh_from_db()
        self.submission.refresh_from_db()
        task = get_or_create_judge_task(answer)

        self.assertEqual(score, Decimal("100"))
        self.assertEqual(answer.judge_status, Answer.JudgeStatus.ACCEPTED)
        self.assertEqual(task.status, JudgeTask.Status.SUCCESS)
        self.assertEqual(self.submission.status, Submission.Status.COMPLETED)
        self.assertEqual(self.submission.total_score, Decimal("100"))


