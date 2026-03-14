from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.exams.models import Exam, ExamQuestion, Question

from .models import Notification

User = get_user_model()


class NotificationApiTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="notify_teacher", password="pass1234", role="teacher", email="teacher@example.com")
        self.student = User.objects.create_user(username="notify_student", password="pass1234", role="student", email="student@example.com")
        self.student2 = User.objects.create_user(username="notify_student2", password="pass1234", role="student", email="student2@example.com")

    def create_exam(self):
        question = Question.objects.create(
            title="Notify Question",
            question_type=Question.QuestionType.SINGLE,
            prompt="1+1?",
            options=["1", "2"],
            correct_answer={"value": "2"},
        )
        now = timezone.now()
        exam = Exam.objects.create(
            title="Notify Exam",
            description="exam publish notification",
            starts_at=now + timedelta(minutes=10),
            ends_at=now + timedelta(hours=2),
            duration_minutes=120,
            status=Exam.Status.DRAFT,
            created_by=self.teacher,
        )
        ExamQuestion.objects.create(exam=exam, question=question, score=100, order=1)
        return exam

    def test_publish_exam_creates_student_notifications(self):
        exam = self.create_exam()
        self.client.force_login(self.teacher)

        response = self.client.post(f"/api/exams/exams/{exam.id}/publish/", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notified_students"], 2)
        self.assertEqual(Notification.objects.filter(category=Notification.Category.EXAM).count(), 2)

    def test_student_can_list_and_mark_notifications_as_read(self):
        exam = self.create_exam()
        self.client.force_login(self.teacher)
        self.client.post(f"/api/exams/exams/{exam.id}/publish/", content_type="application/json")

        self.client.logout()
        self.client.force_login(self.student)
        list_response = self.client.get("/api/notifications/")
        self.assertEqual(list_response.status_code, 200)
        payload = list_response.json()
        self.assertEqual(len(payload["results"]), 1)
        notification_id = payload["results"][0]["id"]
        self.assertFalse(payload["results"][0]["is_read"])

        summary_response = self.client.get("/api/notifications/summary/")
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["unread"], 1)

        read_response = self.client.post(f"/api/notifications/{notification_id}/read/", content_type="application/json")
        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_response.json()["notification"]["is_read"])

        summary_after = self.client.get("/api/notifications/summary/")
        self.assertEqual(summary_after.json()["unread"], 0)

    def test_student_can_mark_all_notifications_as_read(self):
        Notification.objects.create(user=self.student, title="n1", content="c1", status=Notification.Status.SENT)
        Notification.objects.create(user=self.student, title="n2", content="c2", status=Notification.Status.SENT)
        self.client.force_login(self.student)

        response = self.client.post("/api/notifications/read-all/", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 2)
        self.assertEqual(Notification.objects.filter(user=self.student, is_read=True).count(), 2)
