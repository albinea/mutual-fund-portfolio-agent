from rest_framework.test import APITestCase


class PortfolioApiTests(APITestCase):
    def test_portfolio_summary_returns_verified_values(self):
        response = self.client.get("/api/v1/portfolio/summary/?user_id=USER001")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["total_invested"], 110000)
        self.assertEqual(response.data["data"]["current_value"], 125000)
        self.assertEqual(response.data["data"]["fund_count"], 3)

    def test_allocation_rejects_unknown_grouping(self):
        response = self.client.get(
            "/api/v1/portfolio/allocation/?user_id=USER001&group_by=unknown"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "INVALID_INPUT")

    def test_sip_calculator_is_deterministic(self):
        response = self.client.post(
            "/api/v1/calculators/sip/",
            {
                "monthly_investment": 5000,
                "duration_years": 10,
                "expected_annual_return": 12,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["projection"])
        self.assertEqual(response.data["data"]["total_invested"], 600000)
        self.assertGreater(response.data["data"]["expected_wealth"], 600000)

    def test_watchlist_is_scoped_to_the_request_user(self):
        create_response = self.client.post(
            "/api/v1/watchlist/",
            {"user_id": "USER001", "symbol": "C001"},
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        first_user = self.client.get("/api/v1/watchlist/?user_id=USER001")
        second_user = self.client.get("/api/v1/watchlist/?user_id=USER002")

        self.assertEqual(len(first_user.data["data"]["items"]), 1)
        self.assertEqual(second_user.data["data"]["items"], [])

    def test_unconfigured_capability_returns_clear_response(self):
        response = self.client.get("/api/v1/portfolio/changes/")

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.data["error_code"], "DATA_NOT_CONFIGURED")
