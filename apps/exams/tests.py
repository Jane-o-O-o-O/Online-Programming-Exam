from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Submission

User = get_user_model()


class ExamApiTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", password="pass1234", role="teacher")
        self.student = User.objects.create_user(username="student", password="pass1234", role="student")

    def test_create_exam_and_complete_objective_submission(self):
        self.client.force_login(self.teacher)
        question1_response = self.client.post(
            "/api/exams/questions/",
            data={
                "title": "Python output",
                "question_type": "single",
                "prompt": "print(1 + 1)",
                "options": ["1", "2", "3"],
                "correct_answer": {"value": "2"},
                "tags": ["python"],
            },
            content_type="application/json",
        )
        self.assertEqual(question1_response.status_code, 201)
        question1_id = question1_response.json()["id"]

        question2_response = self.client.post(
            "/api/exams/questions/",
            data={
                "title": "Containers",
                "question_type": "multiple",
                "prompt": "Which are Python containers?",
                "options": ["list", "dict", "print"],
                "correct_answer": {"values": ["list", "dict"]},
            },
            content_type="application/json",
        )
        self.assertEqual(question2_response.status_code, 201)
        question2_id = question2_response.json()["id"]

        now = timezone.now()
        exam_response = self.client.post(
            "/api/exams/exams/",
            data={
                "title": "Midterm",
                "description": "objective test",
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=2)).isoformat(),
                "duration_minutes": 120,
                "status": "published",
                "questions": [
                    {"question_id": question1_id, "order": 1, "score": 40},
                    {"question_id": question2_id, "order": 2, "score": 60},
                ],
            },
            content_type="application/json",
        )
        self.assertEqual(exam_response.status_code, 201)
        exam_id = exam_response.json()["id"]

        self.client.logout()
        self.client.force_login(self.student)

        start_response = self.client.post(
            f"/api/exams/exams/{exam_id}/start/",
            content_type="application/json",
        )
        self.assertEqual(start_response.status_code, 201)
        submission_id = start_response.json()["submission_id"]

        save_response = self.client.post(
            f"/api/exams/submissions/{submission_id}/answers/",
            data={
                "answers": [
                    {"question_id": question1_id, "answer_payload": {"value": "2"}},
                    {"question_id": question2_id, "answer_payload": {"values": ["dict", "list"]}},
                ]
            },
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)

        finish_response = self.client.post(
            f"/api/exams/submissions/{submission_id}/finish/",
            content_type="application/json",
        )
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.json()["status"], Submission.Status.COMPLETED)
        self.assertEqual(finish_response.json()["total_score"], 100.0)

        detail_response = self.client.get(f"/api/exams/submissions/{submission_id}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()["answers"]), 2)

    def test_programming_question_sets_submission_to_judging(self):
        self.client.force_login(self.teacher)
        question_response = self.client.post(
            "/api/exams/questions/",
            data={
                "title": "FizzBuzz",
                "question_type": "program",
                "prompt": "Write fizzbuzz",
                "language": "python",
            },
            content_type="application/json",
        )
        self.assertEqual(question_response.status_code, 201)
        question_id = question_response.json()["id"]

        now = timezone.now()
        exam_response = self.client.post(
            "/api/exams/exams/",
            data={
                "title": "Code Exam",
                "starts_at": (now - timedelta(minutes=5)).isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
                "status": "published",
                "questions": [{"question_id": question_id, "score": 100}],
            },
            content_type="application/json",
        )
        self.assertEqual(exam_response.status_code, 201)
        exam_id = exam_response.json()["id"]

        self.client.logout()
        self.client.force_login(self.student)

        start_response = self.client.post(
            f"/api/exams/exams/{exam_id}/start/",
            content_type="application/json",
        )
        self.assertEqual(start_response.status_code, 201)
        submission_id = start_response.json()["submission_id"]

        save_response = self.client.post(
            f"/api/exams/submissions/{submission_id}/answers/",
            data={"answers": [{"question_id": question_id, "source_code": "print('ok')"}]},
            content_type="application/json",
        )
        self.assertEqual(save_response.status_code, 200)

        finish_response = self.client.post(
            f"/api/exams/submissions/{submission_id}/finish/",
            content_type="application/json",
        )
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.json()["status"], Submission.Status.JUDGING)
        self.assertEqual(finish_response.json()["pending_programming"], 1)

    def test_student_cannot_create_exam(self):
        self.client.force_login(self.student)
        response = self.client.post(
            "/api/exams/exams/",
            data={
                "title": "Blocked",
                "starts_at": timezone.now().isoformat(),
                "ends_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
