from decimal import Decimal

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.exams.models import Answer, Exam, ExamQuestion, Question, Submission

from .models import JudgeTask
from .services import judge_program_answer


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
