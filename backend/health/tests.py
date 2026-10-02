from django.test import SimpleTestCase
from django.db.utils import DatabaseError
from unittest.mock import patch


class HealthEndpointTests(SimpleTestCase):
    @patch("health.views.connections")
    def test_reports_database_ready(self, connections):
        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")

    @patch("health.views.connections")
    def test_returns_503_when_database_is_unavailable(self, connections):
        connections.__getitem__.return_value.ensure_connection.side_effect = DatabaseError

        response = self.client.get("/api/v1/health/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(response.json()["database"], "unavailable")
