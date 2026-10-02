from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase


User = get_user_model()


class AccountApiTests(APITestCase):
    def test_signup_creates_account_and_starts_authenticated_session(self):
        response = self.client.post(
            "/api/v1/auth/signup/",
            {
                "email": "investor@example.com",
                "password": "Bright-Mountain-42!",
                "first_name": "Asha",
                "last_name": "Shah",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        account = User.objects.get(email="investor@example.com")
        self.assertTrue(account.check_password("Bright-Mountain-42!"))
        self.assertNotEqual(account.username, "investor@example.com")
        self.assertEqual(response.data["data"]["user_id"], account.username)

        profile = self.client.get("/api/v1/auth/profile/")
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["data"]["email"], "investor@example.com")

    def test_signup_rejects_duplicate_email_and_weak_password(self):
        User.objects.create_user(
            username="existing-account",
            email="existing@example.com",
            password="Initial-Password-82!",
        )
        duplicate = self.client.post(
            "/api/v1/auth/signup/",
            {
                "email": "EXISTING@example.com",
                "password": "Different-Mountain-44!",
                "first_name": "Asha",
            },
            format="json",
        )
        weak = self.client.post(
            "/api/v1/auth/signup/",
            {
                "email": "new@example.com",
                "password": "password",
                "first_name": "Asha",
            },
            format="json",
        )

        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(weak.status_code, 400)
        self.assertEqual(User.objects.count(), 1)

    def test_login_profile_update_and_logout(self):
        User.objects.create_user(
            username="login-account",
            email="login@example.com",
            password="Bright-Mountain-42!",
            first_name="Asha",
        )
        failed = self.client.post(
            "/api/v1/auth/login/",
            {"email": "login@example.com", "password": "incorrect"},
            format="json",
        )
        self.assertEqual(failed.status_code, 400)

        logged_in = self.client.post(
            "/api/v1/auth/login/",
            {"email": "LOGIN@example.com", "password": "Bright-Mountain-42!"},
            format="json",
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.data["data"]["user_id"], "login-account")

        updated = self.client.patch(
            "/api/v1/auth/profile/",
            {"first_name": "Asha Devi", "last_name": "Rao"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["data"]["first_name"], "Asha Devi")
        self.assertEqual(updated.data["data"]["email"], "login@example.com")

        logged_out = self.client.post("/api/v1/auth/logout/", {}, format="json")
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/profile/").status_code, 403)

    def test_private_api_rejects_anonymous_requests(self):
        response = self.client.get("/api/v1/portfolio/summary/?user_id=USER001")
        self.assertEqual(response.status_code, 403)

    def test_reference_disclosure_upload_is_staff_only(self):
        self.client.force_authenticate(
            user=User.objects.create_user(
                username="regular-account",
                email="regular@example.com",
                password="Bright-Mountain-42!",
            )
        )
        response = self.client.post("/api/v1/portfolio/disclosures/import/", {}, format="multipart")
        self.assertEqual(response.status_code, 403)

    def test_csrf_protects_account_creation(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_response = client.get("/api/v1/auth/csrf/")
        self.assertEqual(csrf_response.status_code, 200)

        payload = {
            "email": "csrf@example.com",
            "password": "Bright-Mountain-42!",
            "first_name": "Asha",
        }
        rejected = client.post("/api/v1/auth/signup/", payload, format="json")
        self.assertEqual(rejected.status_code, 403)

        accepted = client.post(
            "/api/v1/auth/signup/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=csrf_response.data["data"]["csrf_token"],
        )
        self.assertEqual(accepted.status_code, 201)
