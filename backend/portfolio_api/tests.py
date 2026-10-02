from io import BytesIO
from unittest.mock import patch

from app.agent.tool_registry import call_tool
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APITestCase

from .models import PortfolioImport


class PortfolioApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="USER001",
            email="user001@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=self.user)

    def enable_disclosure_admin(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_authenticate(user=self.user)

    def test_portfolio_summary_returns_verified_values(self):
        response = self.client.get("/api/v1/portfolio/summary/?user_id=USER001")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["total_invested"], 110000)
        self.assertEqual(response.data["data"]["current_value"], 125000)
        self.assertEqual(response.data["data"]["fund_count"], 3)

    def test_explorer_does_not_mark_demo_funds_as_imported_holdings(self):
        response = self.client.get("/api/v1/portfolio/holdings/?user_id=USER001")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["imported"])
        self.assertEqual(response.data["data"]["source_name"], "Mock portfolio store")

    @patch("portfolio_api.views.tools.search_mutual_fund_schemes")
    def test_fund_explorer_searches_market_scheme_catalogue(self, search_schemes):
        search_schemes.return_value = {
            "success": True,
            "query": "HDFC ELSS",
            "schemes": [{"scheme_code": 12345, "scheme_name": "HDFC ELSS Tax Saver Fund - Direct Plan - Growth"}],
            "source": {"name": "MFapi.in scheme search", "url": "https://api.mfapi.in/mf/search?q=HDFC+ELSS"},
        }

        response = self.client.get("/api/v1/funds/search/?q=HDFC%20ELSS")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["schemes"][0]["scheme_code"], 12345)
        search_schemes.assert_called_once_with("HDFC ELSS", 12)

    def test_fund_explorer_search_requires_a_useful_query(self):
        response = self.client.get("/api/v1/funds/search/?q=a")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "INVALID_INPUT")

    @patch("portfolio_api.views.tools.compare_funds")
    def test_fund_explorer_compares_selected_nav_series(self, compare_funds):
        compare_funds.return_value = {
            "success": True,
            "years": 3,
            "funds": [
                {"scheme_code": 123, "cagr_percent": 12.3, "annualized_volatility_percent": 14.2, "maximum_drawdown_percent": -20.1}
            ],
            "source": {"name": "MFapi.in NAV history"},
        }

        response = self.client.post(
            "/api/v1/funds/nav-compare/",
            {"scheme_codes": [123, 456], "years": 3},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["funds"][0]["cagr_percent"], 12.3)
        compare_funds.assert_called_once_with([123, 456], 3)

    @patch("portfolio_api.views.tools.calculate_cagr")
    @patch("portfolio_api.views.tools.get_nav_history")
    def test_fund_explorer_overview_shows_latest_nav_and_trailing_returns(self, get_history, calculate_cagr):
        get_history.return_value = {
            "success": True,
            "scheme_code": 123,
            "observations": [{"date": "2026-10-01", "nav": 42.5}],
            "total_observations": 1200,
            "source": {"name": "MFapi.in NAV data", "url": "https://api.mfapi.in/mf/123"},
        }
        calculate_cagr.side_effect = [
            {"success": True, "cagr_percent": 10.0, "start_date": "2025-10-01", "end_date": "2026-10-01", "source": {"name": "MFapi.in NAV data"}},
            {"success": False},
            {"success": True, "cagr_percent": 8.0, "start_date": "2021-10-01", "end_date": "2026-10-01", "source": {"name": "MFapi.in NAV data"}},
        ]

        response = self.client.get("/api/v1/funds/nav-overview/123/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["latest_nav"], 42.5)
        self.assertEqual(response.data["data"]["returns"][0]["cagr_percent"], 10.0)
        self.assertIsNone(response.data["data"]["returns"][1]["cagr_percent"])
        self.assertEqual(response.data["data"]["returns"][2]["cagr_percent"], 8.0)

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
        self.assertEqual(len(response.data["data"]["yearly_projection"]), 10)
        self.assertEqual(
            response.data["data"]["yearly_projection"][-1]["expected_wealth"],
            response.data["data"]["expected_wealth"],
        )
        self.assertIn("beginning of each month", response.data["data"]["assumptions"][0])

    def test_expected_wealth_returns_a_yearly_projection_with_assumptions(self):
        response = self.client.post(
            "/api/v1/calculators/expected-wealth/",
            {
                "initial_investment": 100000,
                "additional_investment": 10000,
                "frequency": "monthly",
                "duration_years": 10,
                "expected_annual_return": 12,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(len(data["yearly_projection"]), 10)
        self.assertEqual(data["yearly_projection"][-1]["expected_wealth"], data["expected_wealth"])
        self.assertIn("compounded monthly", data["assumptions"][1])

    @patch("app.tools.core.get_market_data")
    def test_watchlist_is_scoped_to_the_request_user(self, mock_market_data):
        mock_market_data.return_value = {
            "success": True,
            "data": {
                "price": 100,
                "price_change_percentage": 1,
                "timestamp": "2026-10-01",
                "source": "Test provider",
                "data_mode": "Test quote",
            },
        }
        create_response = self.client.post(
            "/api/v1/watchlist/",
            {"user_id": "USER001", "symbol": "C001"},
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        first_user = self.client.get("/api/v1/watchlist/?user_id=USER001")
        spoofed_user = self.client.get("/api/v1/watchlist/?user_id=USER002")

        other_user = get_user_model().objects.create_user(
            username="USER002",
            email="user002@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=other_user)
        second_user = self.client.get("/api/v1/watchlist/?user_id=USER001")

        self.assertEqual(len(first_user.data["data"]["items"]), 1)
        self.assertEqual(len(spoofed_user.data["data"]["items"]), 1)
        self.assertEqual(second_user.data["data"]["items"], [])

    def test_unconfigured_capability_returns_clear_response(self):
        response = self.client.get("/api/v1/market/summary/")

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.data["error_code"], "DATA_NOT_CONFIGURED")

    def test_csv_import_replaces_active_portfolio_for_that_user(self):
        first_statement = SimpleUploadedFile(
            "portfolio.csv",
            b"fund_name,category,units,invested_amount,current_value\nAurora Fund,Equity,10,1000,1200\nCedar Fund,Debt,5,500,525\n",
            content_type="text/csv",
        )
        first_response = self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT001", "file": first_statement},
            format="multipart",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertTrue(first_response.data["success"])
        self.assertEqual(first_response.data["data"]["holding_count"], 2)
        self.assertEqual(PortfolioImport.objects.get().user_id, "USER001")

        summary = self.client.get("/api/v1/portfolio/summary/?user_id=IMPORT001")
        holdings = self.client.get("/api/v1/portfolio/holdings/?user_id=IMPORT001")
        allocation = self.client.get(
            "/api/v1/portfolio/allocation/?user_id=IMPORT001&group_by=category"
        )
        self.assertEqual(summary.data["data"]["total_invested"], 1500)
        self.assertEqual(summary.data["data"]["current_value"], 1725)
        self.assertEqual(holdings.data["data"]["results"][0]["category"], "Equity")
        self.assertTrue(holdings.data["data"]["imported"])
        self.assertTrue(holdings.data["data"]["source_name"].startswith("Imported CSV"))
        self.assertEqual(allocation.data["data"]["items"][0]["name"], "Equity")

        replacement_statement = SimpleUploadedFile(
            "replacement.csv",
            b"fund_name,invested_amount,current_value\nNew Fund,2500,2700\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT001", "file": replacement_statement},
            format="multipart",
        )
        updated_summary = self.client.get(
            "/api/v1/portfolio/summary/?user_id=IMPORT001"
        )
        self.assertEqual(updated_summary.data["data"]["fund_count"], 1)
        self.assertEqual(updated_summary.data["data"]["current_value"], 2700)

    def test_xlsx_import_and_invalid_import_errors(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(["fund_name", "units", "invested_amount", "current_value"])
        worksheet.append(["Excel Fund", 4, 4000, 4400])
        stream = BytesIO()
        workbook.save(stream)
        spreadsheet = SimpleUploadedFile(
            "portfolio.xlsx",
            stream.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

        response = self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT002", "file": spreadsheet},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["data"]["source_format"], "xlsx")

        invalid = SimpleUploadedFile(
            "missing-columns.csv",
            b"fund_name,units\nIncomplete Fund,2\n",
            content_type="text/csv",
        )
        invalid_response = self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT003", "file": invalid},
            format="multipart",
        )
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.data["error_code"], "INVALID_IMPORT")

    def test_changes_compares_two_dated_imports_for_the_same_user(self):
        older_statement = SimpleUploadedFile(
            "september.csv",
            b"fund_name,invested_amount,current_value\nExisting Fund,1000,1100\nRemoved Fund,500,450\n",
            content_type="text/csv",
        )
        newer_statement = SimpleUploadedFile(
            "october.csv",
            b"fund_name,invested_amount,current_value\nExisting Fund,1200,1350\nAdded Fund,800,820\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT004", "as_of_date": "2026-09-01", "file": older_statement},
            format="multipart",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "IMPORT004", "as_of_date": "2026-10-01", "file": newer_statement},
            format="multipart",
        )

        snapshots = self.client.get("/api/v1/portfolio/snapshots/?user_id=IMPORT004")
        changes = self.client.get("/api/v1/portfolio/changes/?user_id=IMPORT004")

        self.assertEqual(snapshots.status_code, 200)
        self.assertEqual(len(snapshots.data["data"]["results"]), 2)
        self.assertTrue(changes.data["data"]["available"])
        rows = {item["fund_name"]: item for item in changes.data["data"]["changes"]}
        self.assertEqual(rows["Existing Fund"]["change_type"], "Increased")
        self.assertEqual(rows["Added Fund"]["change_type"], "Added")
        self.assertEqual(rows["Removed Fund"]["change_type"], "Removed")

    def test_disclosure_upload_calculates_overlap_for_an_imported_portfolio(self):
        self.enable_disclosure_admin()
        statement = SimpleUploadedFile(
            "portfolio.csv",
            b"fund_name,invested_amount,current_value\nAlpha Fund,6000,6000\nBeta Fund,4000,4000\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "OVERLAP001", "file": statement},
            format="multipart",
        )
        disclosures = SimpleUploadedFile(
            "fund-disclosures.csv",
            (
                b"fund_name,company_name,isin,holding_weight,sector\n"
                b"Alpha Fund,Shared Bank,INE000A01001,10,Financial Services\n"
                b"Alpha Fund,Alpha Industries,INE000A01002,5,Industrials\n"
                b"Beta Fund,Shared Bank,INE000A01001,20,Financial Services\n"
                b"Beta Fund,Beta Software,INE000A01003,8,Information Technology\n"
            ),
            content_type="text/csv",
        )
        import_response = self.client.post(
            "/api/v1/portfolio/disclosures/import/",
            {
                "file": disclosures,
                "disclosure_date": "2026-08-31",
                "source_name": "AMFI demo disclosure",
                "source_url": "https://www.amfiindia.com/online-center/portfolio-disclosure",
            },
            format="multipart",
        )

        self.assertEqual(import_response.status_code, 201)
        self.assertEqual(import_response.data["data"]["holding_count"], 4)

        overlap = self.client.get("/api/v1/portfolio/overlap/?user_id=OVERLAP001")
        sector_allocation = self.client.get(
            "/api/v1/portfolio/allocation/?user_id=OVERLAP001&group_by=sector"
        )

        self.assertEqual(overlap.status_code, 200)
        self.assertEqual(overlap.data["data"]["overall_overlap_percent"], 14.0)
        self.assertEqual(overlap.data["data"]["companies"][0]["company"], "Shared Bank")
        self.assertEqual(len(overlap.data["data"]["companies"][0]["funds"]), 2)
        self.assertEqual(sector_allocation.status_code, 200)
        self.assertEqual(sector_allocation.data["data"]["items"][0]["name"], "Financial Services")

        # The chat agent calls this same registry. It must use the imported
        # statement/disclosures, not the Aurora/Cedar development fixtures.
        agent_portfolio = call_tool("get_portfolio", {}, user_id="USER001")
        agent_exposure = call_tool("calculate_exposure", {}, user_id="USER001")
        agent_overlap = call_tool("calculate_fund_overlap", {}, user_id="USER001")

        self.assertEqual(agent_portfolio["current_value"], 10000.0)
        self.assertEqual(agent_portfolio["funds"][0]["fund_name"], "Alpha Fund")
        self.assertEqual(agent_exposure["exposures"][0]["company"], "Shared Bank")
        self.assertEqual(agent_exposure["exposures"][0]["fund_count"], 2)
        self.assertEqual(agent_overlap["overlapping_companies"][0]["company_name"], "Shared Bank")
        self.assertEqual(agent_overlap["overall_overlap_percent"], 14.0)
        self.assertEqual(agent_overlap["source"]["name"], "AMFI demo disclosure")

    def test_imported_portfolio_requires_disclosures_for_each_fund(self):
        self.enable_disclosure_admin()
        statement = SimpleUploadedFile(
            "portfolio.csv",
            b"fund_name,invested_amount,current_value\nMapped Fund,1000,1200\nMissing Fund,2000,2200\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "MISSING001", "file": statement},
            format="multipart",
        )
        disclosures = SimpleUploadedFile(
            "fund-disclosures.csv",
            b"fund_name,company_name,holding_weight\nMapped Fund,Example Company,12\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/disclosures/import/",
            {"file": disclosures},
            format="multipart",
        )

        overlap = self.client.get("/api/v1/portfolio/overlap/?user_id=MISSING001")

        self.assertEqual(overlap.status_code, 422)
        self.assertEqual(overlap.data["error_code"], "DATA_UNAVAILABLE")
        self.assertIn("Missing Fund", overlap.data["message"])

        agent_overlap = call_tool("calculate_fund_overlap", {}, user_id="USER001")
        self.assertFalse(agent_overlap["success"])
        self.assertEqual(agent_overlap["error_code"], "DATA_UNAVAILABLE")
        self.assertIn("Missing Fund", agent_overlap["message"])

    def test_company_exposure_uses_imported_disclosures(self):
        self.enable_disclosure_admin()
        statement = SimpleUploadedFile(
            "portfolio.csv",
            b"fund_name,invested_amount,current_value\nAlpha Fund,6000,6000\nBeta Fund,4000,4000\n",
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/import/",
            {"user_id": "COMPANY001", "file": statement},
            format="multipart",
        )
        disclosures = SimpleUploadedFile(
            "fund-disclosures.csv",
            (
                b"fund_name,company_name,holding_weight,sector\n"
                b"Alpha Fund,HDFC Bank,10,Financial Services\n"
                b"Beta Fund,HDFC Bank,20,Financial Services\n"
            ),
            content_type="text/csv",
        )
        self.client.post(
            "/api/v1/portfolio/disclosures/import/",
            {
                "file": disclosures,
                "disclosure_date": "2026-08-31",
                "source_name": "Fund disclosure test data",
            },
            format="multipart",
        )

        response = self.client.get(
            "/api/v1/companies/C001/fund-exposure/?user_id=COMPANY001"
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["company"]["name"], "HDFC Bank")
        self.assertEqual(data["user_portfolio_exposure_percent"], 14.0)
        self.assertEqual(len(data["funds_holding_company"]), 2)
        self.assertEqual(data["data_as_of"], "2026-08-31")
        self.assertEqual(data["source_names"], ["Fund disclosure test data"])
