from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from apps.notifications.models import Notification
from apps.notifications.services import clear_password_reset_state, get_password_reset_state

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountApiTests(TestCase):
    def tearDown(self):
        clear_password_reset_state("student@example.com")

    def test_register_login_me_and_logout(self):
        register_response = self.client.post(
            "/api/accounts/register/",
            data={
                "username": "student1",
                "password": "pass1234",
                "role": "student",
                "real_name": "Student One",
                "email": "student1@example.com",
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
        student = User.objects.create_user(username="student", password="pass1234", role="student", email="student@example.com")
        teacher = User.objects.create_user(username="teacher", password="pass1234", role="teacher", email="teacher@example.com")

        self.client.force_login(student)
        student_response = self.client.get("/api/accounts/stats/")
        self.assertEqual(student_response.status_code, 403)

        self.client.logout()
        self.client.force_login(teacher)
        teacher_response = self.client.get("/api/accounts/stats/")
        self.assertEqual(teacher_response.status_code, 200)
        self.assertEqual(teacher_response.json()["students"], 1)

    def test_send_reset_code_and_reset_password(self):
        user = User.objects.create_user(username="student", password="oldpass1", role="student", email="student@example.com")

        send_response = self.client.post(
            "/api/accounts/password-reset-code/",
            data={"username": "student", "email": "student@example.com"},
            content_type="application/json",
        )
        self.assertEqual(send_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.first().status, Notification.Status.SENT)

        state = get_password_reset_state("student@example.com")
        self.assertIsNotNone(state)
        code = state["code"]

        reset_response = self.client.post(
            "/api/accounts/password-reset/",
            data={
                "username": "student",
                "email": "student@example.com",
                "code": code,
                "new_password": "newpass1",
            },
            content_type="application/json",
        )
        self.assertEqual(reset_response.status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.check_password("newpass1"))
        self.assertIsNone(get_password_reset_state("student@example.com"))

    def test_reset_password_rejects_wrong_code(self):
        User.objects.create_user(username="student", password="oldpass1", role="student", email="student@example.com")
        self.client.post(
            "/api/accounts/password-reset-code/",
            data={"username": "student", "email": "student@example.com"},
            content_type="application/json",
        )

        reset_response = self.client.post(
            "/api/accounts/password-reset/",
            data={
                "username": "student",
                "email": "student@example.com",
                "code": "000000",
                "new_password": "newpass1",
            },
            content_type="application/json",
        )
        self.assertEqual(reset_response.status_code, 400)
        self.assertEqual(reset_response.json()["error"], "invalid verification code")
