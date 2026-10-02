from app.tools import core as t
from unittest.mock import patch


class _NavResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": [
                {"date": "01-01-2026", "nav": "140"},
                {"date": "01-01-2025", "nav": "120"},
                {"date": "01-01-2024", "nav": "110"},
                {"date": "01-01-2023", "nav": "100"},
            ]
        }


class _MarketResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "symbol": "HDFCBANK",
            "exchange": "NSE",
            "currency": "INR",
            "close": "1750.50",
            "previous_close": "1700.00",
            "percent_change": "2.9706",
            "datetime": "2026-10-01",
        }


class _Response:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _YahooSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == "https://fc.yahoo.com":
            return _Response()
        if url.endswith("/v1/test/getcrumb"):
            return _Response(text="crumb-value")
        return _Response(
            {
                "quoteResponse": {
                    "result": [
                        {"symbol": "HDFCBANK.NS", "fullExchangeName": "NSE", "currency": "INR", "regularMarketPrice": 950.25, "regularMarketChangePercent": 1.25, "regularMarketTime": 1790847900, "exchangeDataDelayedBy": 15},
                        {"symbol": "RELIANCE.NS", "fullExchangeName": "NSE", "currency": "INR", "regularMarketPrice": 1400.0, "regularMarketChangePercent": -0.5, "regularMarketTime": 1790847900, "exchangeDataDelayedBy": 15},
                    ]
                }
            }
        )

def test_portfolio_totals():
    p=t.get_portfolio("USER001")
    assert p["success"] and p["total_invested"]==110000 and p["current_value"]==125000

def test_effective_exposure():
    r=t.calculate_exposure("USER001","C001")["exposures"][0]
    assert r["exposure_value"]==10300
    assert round(r["portfolio_weight_percentage"],2)==8.24

def test_overlap_and_sector_exposure():
    overlap=t.calculate_fund_overlap("USER001")["overlapping_companies"]
    bank=next(x for x in overlap if x["company_id"]=="C001")
    assert bank["fund_count"]==3 and bank["effective_portfolio_exposure"]==8.24
    sectors=t.calculate_sector_exposure("USER001")["sectors"]
    financial=next(x for x in sectors if x["sector"]=="Financial Services")
    assert financial["value"]==14530

def test_simulation_conserves_value():
    result=t.simulate_allocation("USER001",30000,{"F001":5000,"F002":10000,"F003":15000})
    assert result["success"] and result["after"]["total_value"]==155000
    assert round(sum(x["percentage"] for x in result["after"]["fund_allocation"]),6)==100

def test_errors_and_validation():
    assert t.get_portfolio("absent")["error_code"]=="PORTFOLIO_NOT_FOUND"
    v=t.validate_analysis(["Guaranteed return of 20%"],[{}])
    assert not v["valid"] and len(v["issues"])==2


@patch("app.tools.nav.requests.get", return_value=_NavResponse())
def test_public_nav_analytics(mock_get):
    from app.tools import nav
    nav._nav_cache.clear()
    cagr=t.calculate_cagr(119551,3)
    volatility=t.calculate_volatility(119551,3)
    drawdown=t.calculate_drawdown(119551,3)
    comparison=t.compare_funds([119551,119552],3)
    assert cagr["success"] and cagr["cagr_percent"]==11.87
    assert volatility["success"] and volatility["annualized_volatility_percent"]>0
    assert drawdown["success"] and drawdown["maximum_drawdown_percent"]==0
    assert comparison["success"] and len(comparison["funds"])==2
    # Several analytics in one process reuse the short-lived NAV history cache.
    assert mock_get.call_count==2


def test_mfapi_scheme_lookup_refuses_ambiguous_plan_variants(monkeypatch):
    from app.tools import nav

    nav._search_cache.clear()
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response([
            {"schemeCode": 101, "schemeName": "HDFC ELSS Tax Saver Fund - Direct Plan - Growth"},
            {"schemeCode": 102, "schemeName": "HDFC ELSS Tax Saver Fund - Regular Plan - Growth"},
        ])

    monkeypatch.setattr(nav.requests, "get", fake_get)
    result = t.get_mutual_fund_nav("HDFC ELSS Tax Saver Fund")

    assert result["error_code"] == "FUND_AMBIGUOUS"
    assert [item["scheme_code"] for item in result["candidates"]] == [101, 102]
    assert len(calls) == 1


def test_mfapi_latest_nav_by_exact_scheme_name_has_provider_source(monkeypatch):
    from app.tools import nav

    nav._search_cache.clear()
    nav._latest_cache.clear()
    search_payload = [{
        "schemeCode": 8001,
        "schemeName": "HDFC ELSS Tax Saver Fund - Regular Plan - Growth",
    }]

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        if url.endswith("/search"):
            return Response(search_payload)
        assert url.endswith("/8001/latest")
        return Response({
            "meta": {"scheme_code": 8001, "scheme_name": search_payload[0]["schemeName"]},
            "data": [{"date": "01-10-2026", "nav": "250.12500"}],
            "status": "SUCCESS",
        })

    monkeypatch.setattr(nav.requests, "get", fake_get)
    result = t.get_mutual_fund_nav("HDFC ELSS Tax Saver Fund - Regular Plan - Growth")

    assert result["success"]
    assert result["scheme_code"] == 8001
    assert result["nav"] == 250.125
    assert result["nav_date"] == "2026-10-01"
    assert "MFapi.in" in result["source"]["name"]
    assert result["source"]["data_as_of"] == "2026-10-01"


def test_mfapi_calculates_lump_sum_value_from_inception_with_effective_dates(monkeypatch):
    from app.tools import nav

    nav._search_cache.clear()
    nav._nav_cache.clear()
    search_payload = [{
        "schemeCode": 8002,
        "schemeName": "HDFC ELSS Tax Saver Fund - Regular Plan - Growth",
    }]

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        if url.endswith("/search"):
            return Response(search_payload)
        return Response({
            "meta": {"scheme_code": 8002, "scheme_name": search_payload[0]["schemeName"]},
            "data": [
                {"date": "01-01-2023", "nav": "100"},
                {"date": "01-01-2024", "nav": "115"},
                {"date": "01-10-2026", "nav": "140"},
            ],
        })

    monkeypatch.setattr(nav.requests, "get", fake_get)
    result = t.calculate_lump_sum_value("HDFC ELSS Tax Saver Fund - Regular Plan - Growth")

    assert result["success"]
    assert result["estimated_value"] == 14000
    assert result["start_date"] == "2023-01-01"
    assert result["end_date"] == "2026-10-01"
    assert "not an SIP" in result["methodology"]
    invalid_range = t.calculate_lump_sum_value(
        "HDFC ELSS Tax Saver Fund - Regular Plan - Growth",
        start_date="2026-10-02",
        end_date="2026-10-01",
    )
    assert invalid_range["error_code"] == "INVALID_INPUT"


@patch("app.tools.core.requests.get", return_value=_MarketResponse())
def test_twelve_data_quote_uses_configured_symbol_and_preserves_provider_metadata(mock_get, monkeypatch):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "test-key")
    t.MarketDataProvider._cache.clear()

    quote = t.get_market_data("C001")

    assert quote["success"]
    assert quote["data"]["price"] == 1750.50
    assert quote["data"]["price_change_percentage"] == 2.9706
    assert quote["data"]["data_mode"] == "Latest available quote (Indian exchange coverage may be EOD)"
    assert quote["source"]["name"] == "Twelve Data"
    assert mock_get.call_args.kwargs["params"]["symbol"] == "HDFCBANK"
    assert mock_get.call_args.kwargs["params"]["exchange"] == "NSE"


def test_community_market_fallback_batches_unavailable_nse_quotes():
    t.CommunityMarketDataProvider._cache.clear()
    session = _YahooSession()
    provider = t.CommunityMarketDataProvider(session=session)

    quotes = provider.get_many(["C001", "C002"])

    assert quotes["C001"]["price"] == 950.25
    assert quotes["C002"]["price_change_percentage"] == -0.5
    assert quotes["C001"]["source"] == "Community fallback via Yahoo Finance"
    assert len(session.calls) == 3
    assert session.calls[-1][0] == "https://query1.finance.yahoo.com/v7/finance/quote"
    assert session.calls[-1][1]["params"]["symbols"] == "HDFCBANK.NS,RELIANCE.NS"
