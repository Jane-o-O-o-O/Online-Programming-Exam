from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Answer, Submission

User = get_user_model()


@override_settings(JUDGE_EXECUTION_MODE="local")
class ExamApiTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", password="pass1234", role="teacher", email="teacher@example.com")
        self.student = User.objects.create_user(username="student", password="pass1234", role="student", email="student@example.com")
        self.student2 = User.objects.create_user(username="student2", password="pass1234", role="student", email="student2@example.com")

    def create_question(self, title="Python output", question_type="single", **overrides):
        payload = {
            "title": title,
            "question_type": question_type,
            "prompt": overrides.pop("prompt", "sample prompt"),
            "options": overrides.pop("options", []),
            "correct_answer": overrides.pop("correct_answer", {}),
            "language": overrides.pop("language", ""),
        }
        payload.update(overrides)
        response = self.client.post("/api/exams/questions/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def create_exam(self, question_items, **overrides):
        now = timezone.now()
        payload = {
            "title": overrides.pop("title", "Midterm"),
            "description": overrides.pop("description", "objective test"),
            "starts_at": overrides.pop("starts_at", (now - timedelta(minutes=5)).isoformat()),
            "ends_at": overrides.pop("ends_at", (now + timedelta(hours=2)).isoformat()),
            "duration_minutes": overrides.pop("duration_minutes", 120),
            "status": overrides.pop("status", "published"),
            "questions": question_items,
        }
        payload.update(overrides)
        response = self.client.post("/api/exams/exams/", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def test_create_exam_and_complete_objective_submission(self):
        self.client.force_login(self.teacher)
        question1_id = self.create_question(
            title="Python output",
            question_type="single",
            prompt="print(1 + 1)",
            options=["1", "2", "3"],
            correct_answer={"value": "2"},
            tags=["python"],
        )
        question2_id = self.create_question(
            title="Containers",
            question_type="multiple",
            prompt="Which are Python containers?",
            options=["list", "dict", "print"],
            correct_answer={"values": ["list", "dict"]},
        )
        exam_id = self.create_exam([
            {"question_id": question1_id, "order": 1, "score": 40},
            {"question_id": question2_id, "order": 2, "score": 60},
        ])

        self.client.logout()
        self.client.force_login(self.student)

        start_response = self.client.post(f"/api/exams/exams/{exam_id}/start/", content_type="application/json")
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

        finish_response = self.client.post(f"/api/exams/submissions/{submission_id}/finish/", content_type="application/json")
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.json()["status"], Submission.Status.COMPLETED)
        self.assertEqual(finish_response.json()["total_score"], 100.0)

    def test_programming_question_is_judged_locally(self):
        self.client.force_login(self.teacher)
        question_id = self.create_question(
            title="FizzBuzz",
            question_type="program",
            prompt="Read n and print n*2",
            language="python",
            correct_answer={
                "cases": [
                    {"input": "2\n", "output": "4\n"},
                    {"input": "5\n", "output": "10\n"},
                ],
                "time_limit_seconds": 1,
            },
        )
        exam_id = self.create_exam([{"question_id": question_id, "score": 100}], title="Code Exam")

        self.client.logout()
        self.client.force_login(self.student)

        start_response = self.client.post(f"/api/exams/exams/{exam_id}/start/", content_type="application/json")
        submission_id = start_response.json()["submission_id"]
        self.client.post(
            f"/api/exams/submissions/{submission_id}/answers/",
            data={"answers": [{"question_id": question_id, "source_code": "n = int(input())\nprint(n * 2)"}]},
            content_type="application/json",
        )
        finish_response = self.client.post(f"/api/exams/submissions/{submission_id}/finish/", content_type="application/json")
        self.assertEqual(finish_response.json()["status"], Submission.Status.COMPLETED)
        self.assertEqual(finish_response.json()["pending_programming"], 0)

        detail_response = self.client.get(f"/api/exams/submissions/{submission_id}/")
        answer = detail_response.json()["answers"][0]
        self.assertEqual(answer["judge_status"], Answer.JudgeStatus.ACCEPTED)
        self.assertEqual(answer["judge_result"]["final_status"], Answer.JudgeStatus.ACCEPTED)

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

    def test_student_question_list_hides_correct_answer(self):
        self.client.force_login(self.teacher)
        self.create_question(
            title="Secret Answer",
            question_type="single",
            prompt="What is 1+1?",
            options=["1", "2"],
            correct_answer={"value": "2"},
        )
        self.client.logout()
        self.client.force_login(self.student)

        response = self.client.get("/api/exams/questions/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("correct_answer", response.json()["results"][0])

    def test_teacher_can_update_publish_finish_exam_and_list_submissions(self):
        self.client.force_login(self.teacher)
        question_id = self.create_question(
            title="Editable Question",
            question_type="single",
            prompt="Old prompt",
            options=["A", "B"],
            correct_answer={"value": "A"},
        )
        exam_id = self.create_exam([{"question_id": question_id, "score": 100}], status="draft", title="Draft Exam")

        update_question_response = self.client.put(
            f"/api/exams/questions/{question_id}/",
            data={"prompt": "New prompt", "tags": ["updated"]},
            content_type="application/json",
        )
        self.assertEqual(update_question_response.status_code, 200)
        self.assertEqual(update_question_response.json()["prompt"], "New prompt")

        update_exam_response = self.client.put(
            f"/api/exams/exams/{exam_id}/",
            data={"title": "Updated Exam", "duration_minutes": 60},
            content_type="application/json",
        )
        self.assertEqual(update_exam_response.status_code, 200)
        self.assertEqual(update_exam_response.json()["title"], "Updated Exam")

        publish_response = self.client.post(f"/api/exams/exams/{exam_id}/publish/", content_type="application/json")
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["status"], "published")

        self.client.logout()
        self.client.force_login(self.student)
        start_response = self.client.post(f"/api/exams/exams/{exam_id}/start/", content_type="application/json")
        self.assertEqual(start_response.status_code, 201)

        self.client.logout()
        self.client.force_login(self.teacher)
        submissions_response = self.client.get(f"/api/exams/exams/{exam_id}/submissions/")
        self.assertEqual(submissions_response.status_code, 200)
        self.assertEqual(len(submissions_response.json()["results"]), 1)

        finish_response = self.client.post(f"/api/exams/exams/{exam_id}/finish/", content_type="application/json")
        self.assertEqual(finish_response.status_code, 200)
        self.assertEqual(finish_response.json()["status"], "finished")

    def test_question_in_use_cannot_be_deleted(self):
        self.client.force_login(self.teacher)
        question_id = self.create_question(
            title="Used Question",
            question_type="single",
            prompt="Use me",
            options=["A", "B"],
            correct_answer={"value": "A"},
        )
        self.create_exam([{"question_id": question_id, "score": 100}], title="Uses Question")

        delete_response = self.client.delete(f"/api/exams/questions/{question_id}/")
        self.assertEqual(delete_response.status_code, 409)

    def test_teacher_can_view_exam_analytics(self):
        self.client.force_login(self.teacher)
        q1 = self.create_question(
            title="Q1",
            question_type="single",
            prompt="1+1?",
            options=["1", "2"],
            correct_answer={"value": "2"},
        )
        q2 = self.create_question(
            title="Q2",
            question_type="single",
            prompt="2+2?",
            options=["3", "4"],
            correct_answer={"value": "4"},
        )
        exam_id = self.create_exam([
            {"question_id": q1, "score": 50},
            {"question_id": q2, "score": 50},
        ], title="Analytics Exam")

        self.client.logout()
        self.client.force_login(self.student)
        sub1 = self.client.post(f"/api/exams/exams/{exam_id}/start/", content_type="application/json").json()["submission_id"]
        self.client.post(
            f"/api/exams/submissions/{sub1}/answers/",
            data={"answers": [{"question_id": q1, "answer_payload": {"value": "2"}}, {"question_id": q2, "answer_payload": {"value": "4"}}]},
            content_type="application/json",
        )
        self.client.post(f"/api/exams/submissions/{sub1}/finish/", content_type="application/json")

        self.client.logout()
        self.client.force_login(self.student2)
        sub2 = self.client.post(f"/api/exams/exams/{exam_id}/start/", content_type="application/json").json()["submission_id"]
        self.client.post(
            f"/api/exams/submissions/{sub2}/answers/",
            data={"answers": [{"question_id": q1, "answer_payload": {"value": "1"}}, {"question_id": q2, "answer_payload": {"value": "4"}}]},
            content_type="application/json",
        )
        self.client.post(f"/api/exams/submissions/{sub2}/finish/", content_type="application/json")

        self.client.logout()
        self.client.force_login(self.teacher)
        analytics_response = self.client.get(f"/api/exams/exams/{exam_id}/analytics/")
        self.assertEqual(analytics_response.status_code, 200)
        payload = analytics_response.json()
        self.assertEqual(payload["summary"]["submission_count"], 2)
        self.assertEqual(payload["summary"]["completed_count"], 2)
        self.assertEqual(payload["summary"]["highest_score"], 100.0)
        self.assertEqual(payload["summary"]["lowest_score"], 50.0)
        self.assertEqual(payload["leaderboard"][0]["username"], "student")
        self.assertEqual(len(payload["question_stats"]), 2)
        self.assertEqual(payload["question_stats"][0]["accuracy_rate"], 0.5)
