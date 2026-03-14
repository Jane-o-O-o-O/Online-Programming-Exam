from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class AccountApiTests(TestCase):
    def test_register_login_me_and_logout(self):
        register_response = self.client.post(
            "/api/accounts/register/",
            data={
                "username": "student1",
                "password": "pass1234",
                "role": "student",
                "real_name": "Student One",
            },
            content_type="application/json",
        )
        self.assertEqual(register_response.status_code, 201)
        self.assertEqual(register_response.json()["user"]["username"], "student1")

        me_response = self.client.get("/api/accounts/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["role"], "student")

        logout_response = self.client.post("/api/accounts/logout/", content_type="application/json")
        self.assertEqual(logout_response.status_code, 200)

        me_after_logout = self.client.get("/api/accounts/me/")
        self.assertEqual(me_after_logout.status_code, 401)

        login_response = self.client.post(
            "/api/accounts/login/",
            data={"username": "student1", "password": "pass1234"},
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["user"]["username"], "student1")

    def test_stats_requires_teacher_or_admin(self):
        student = User.objects.create_user(username="student", password="pass1234", role="student")
        teacher = User.objects.create_user(username="teacher", password="pass1234", role="teacher")

        self.client.force_login(student)
        student_response = self.client.get("/api/accounts/stats/")
        self.assertEqual(student_response.status_code, 403)

        self.client.logout()
        self.client.force_login(teacher)
        teacher_response = self.client.get("/api/accounts/stats/")
        self.assertEqual(teacher_response.status_code, 200)
        self.assertEqual(teacher_response.json()["students"], 1)
