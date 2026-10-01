from __future__ import annotations

from datetime import date
from typing import Any

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from app.tools import core as tools

from .models import WatchlistItem
from .serializers import (
    ApiEnvelopeSerializer,
    ExpectedWealthRequestSerializer,
    FundComparisonRequestSerializer,
    SipRequestSerializer,
    WatchlistCreateSerializer,
)


def _sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    if result.get("sources"):
        return result["sources"]
    return [result["source"]] if result.get("source") else []


def _status_for_error(code: str | None) -> int:
    if code in {"PORTFOLIO_NOT_FOUND", "FUND_NOT_FOUND", "COMPANY_NOT_FOUND"}:
        return status.HTTP_404_NOT_FOUND
    if code in {"INVALID_INPUT"}:
        return status.HTTP_400_BAD_REQUEST
    if code in {"DATA_UNAVAILABLE", "PROVIDER_UNAVAILABLE", "PROVIDER_NOT_CONFIGURED"}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _success(
    data: dict[str, Any] | list[Any],
    sources: list[dict[str, Any]] | None = None,
    message: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    return Response(
        {"success": True, "data": data, "sources": sources or [], "message": message},
        status=status_code,
    )


def _tool_result(result: dict[str, Any], data: dict[str, Any] | list[Any]) -> Response:
    if not result.get("success"):
        return Response(
            {
                "success": False,
                "error_code": result.get("error_code", "TOOL_FAILURE"),
                "message": result.get("message", "The request could not be completed."),
            },
            status=_status_for_error(result.get("error_code")),
        )
    return _success(data, _sources(result), result.get("message"))


def _required_user_id(request) -> str | None:
    return request.query_params.get("user_id") or request.data.get("user_id")


class PortfolioSummaryView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        user_id = _required_user_id(request)
        if not user_id:
            return Response({"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}, status=400)
        result = tools.get_portfolio(user_id)
        if not result.get("success"):
            return _tool_result(result, {})
        total_invested = result["total_invested"]
        current_value = result["current_value"]
        exposure = tools.calculate_exposure(user_id)
        return _tool_result(result, {
            "portfolio_id": user_id,
            "total_invested": total_invested,
            "current_value": current_value,
            "change": round(current_value - total_invested, 2),
            "change_percent": round((current_value - total_invested) / total_invested * 100, 2) if total_invested else 0,
            "fund_count": len(result["funds"]),
            "company_count": len(exposure.get("exposures", [])) if exposure.get("success") else None,
            "currency": "INR",
            "as_of": result["source"].get("data_as_of"),
        })


class PortfolioHoldingsView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True), OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY), OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY), OpenApiParameter("sort", OpenApiTypes.STR, OpenApiParameter.QUERY)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        user_id = _required_user_id(request)
        result = tools.get_portfolio(user_id) if user_id else {"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}
        if not result.get("success"):
            return _tool_result(result, {})
        search = request.query_params.get("search", "").casefold()
        category = request.query_params.get("category", "").casefold()
        rows = []
        for holding in result["funds"]:
            details = tools.store.funds().get(holding["fund_id"], {})
            row = {
                "fund_id": holding["fund_id"], "fund_name": holding["fund_name"],
                "category": details.get("category"), "units": holding["units"],
                "invested_amount": holding["invested_amount"], "current_value": holding["current_value"],
                "allocation_percent": holding["allocation_percentage"],
            }
            if search and search not in row["fund_name"].casefold():
                continue
            if category and category != (row["category"] or "").casefold():
                continue
            rows.append(row)
        sort = request.query_params.get("sort", "-current_value")
        allowed = {"current_value", "invested_amount", "allocation_percent", "fund_name"}
        field = sort.lstrip("-")
        if field in allowed:
            rows.sort(key=lambda row: row[field], reverse=sort.startswith("-"))
        return _tool_result(result, {"results": rows, "total": len(rows)})


class PortfolioAllocationView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True), OpenApiParameter("group_by", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        user_id = _required_user_id(request)
        group_by = request.query_params.get("group_by", "")
        if group_by not in {"fund", "category", "sector", "company"}:
            return Response({"success": False, "error_code": "INVALID_INPUT", "message": "group_by must be fund, category, sector, or company."}, status=400)
        portfolio = tools.get_portfolio(user_id) if user_id else {"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}
        if not portfolio.get("success"):
            return _tool_result(portfolio, {})
        if group_by == "fund":
            items = [{"name": item["fund_name"], "value": item["current_value"], "percentage": item["allocation_percentage"], "funds": [item["fund_name"]]} for item in portfolio["funds"]]
        elif group_by == "sector":
            result = tools.calculate_sector_exposure(user_id)
            if not result.get("success"):
                return _tool_result(result, {})
            items = [{"name": item["sector"], "value": item["value"], "percentage": item["percentage"], "funds": []} for item in result["sectors"]]
        elif group_by == "company":
            result = tools.calculate_exposure(user_id)
            if not result.get("success"):
                return _tool_result(result, {})
            items = [{"name": item["company"], "value": item["exposure_value"], "percentage": item["portfolio_weight_percentage"], "funds": []} for item in result["exposures"]]
        else:
            totals: dict[str, float] = {}
            names: dict[str, list[str]] = {}
            total = portfolio["current_value"]
            for item in portfolio["funds"]:
                category = tools.store.funds().get(item["fund_id"], {}).get("category", "Unknown")
                totals[category] = totals.get(category, 0) + item["current_value"]
                names.setdefault(category, []).append(item["fund_name"])
            items = [{"name": key, "value": round(value, 2), "percentage": round(value / total * 100, 4) if total else 0, "funds": names[key]} for key, value in totals.items()]
        return _tool_result(portfolio, {"group_by": group_by, "items": items, "as_of": portfolio["source"].get("data_as_of")})


class PortfolioOverlapView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        user_id = _required_user_id(request)
        result = tools.calculate_fund_overlap(user_id) if user_id else {"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}
        if not result.get("success"):
            return _tool_result(result, {})
        companies = [
            {"company": item["company_name"], "combined_exposure_percent": item["effective_portfolio_exposure"], "funds": [{"fund_name": name} for name in item["funds"]]}
            for item in result["overlapping_companies"]
        ]
        return _tool_result(result, {
            "overall_overlap_percent": round(sum(item["effective_portfolio_exposure"] for item in result["overlapping_companies"]), 4),
            "explanation": "Companies held through more than one fund are listed below. The percentage is the sum of portfolio exposure to those overlapping companies.",
            "companies": companies,
        })


class FundsView(APIView):
    @extend_schema(operation_id="fund-list", parameters=[OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY), OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY), OpenApiParameter("risk", OpenApiTypes.STR, OpenApiParameter.QUERY), OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY), OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        search = request.query_params.get("search", "").casefold()
        category = request.query_params.get("category", "").casefold()
        risk = request.query_params.get("risk", "").casefold()
        rows = []
        for fund_id, fund in tools.store.funds().items():
            if search and search not in fund["name"].casefold():
                continue
            if category and category != fund.get("category", "").casefold():
                continue
            if risk and risk != fund.get("riskometer", "").casefold():
                continue
            rows.append({"fund_id": fund_id, "fund_name": fund["name"], "category": fund.get("category"), "risk_level": fund.get("riskometer"), "return_3y": None, "expense_ratio": fund.get("expense_ratio"), "fund_size": fund.get("aum_crore"), "risk_adjusted_rating": None, "as_of": fund.get("latest_portfolio_date")})
        sort = request.query_params.get("sort", "fund_name")
        if sort.lstrip("-") in {"fund_name", "expense_ratio", "fund_size"}:
            rows.sort(key=lambda item: item[sort.lstrip("-")] if item[sort.lstrip("-")] is not None else float("inf"), reverse=sort.startswith("-"))
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(max(int(request.query_params.get("page_size", 20)), 1), 100)
        start = (page - 1) * page_size
        return _success({"results": rows[start:start + page_size], "total": len(rows), "page": page, "page_size": page_size}, [{"name": "Mock fund master", "data_as_of": date.today().isoformat()}])


class FundDetailView(APIView):
    @extend_schema(operation_id="fund-detail", responses={200: ApiEnvelopeSerializer})
    def get(self, request, fund_id):
        result = tools.get_mutual_fund_details(fund_id)
        if not result.get("success"):
            return _tool_result(result, {})
        fund = result["details"]
        return _tool_result(result, {
            "fund_id": fund_id, "fund_name": fund["name"], "category": fund.get("category"), "risk_level": fund.get("riskometer"),
            "returns": {"one_year": None, "three_year": None, "five_year": None},
            "risk_adjusted_return": None, "expense_ratio": fund.get("expense_ratio"), "fund_size": fund.get("aum_crore"),
            "manager": {"name": fund.get("fund_manager"), "tenure_years": None}, "benchmark": fund.get("benchmark"), "as_of": fund.get("latest_portfolio_date"),
        })


class FundCompareView(APIView):
    @extend_schema(request=FundComparisonRequestSerializer, responses={200: ApiEnvelopeSerializer})
    def post(self, request):
        serializer = FundComparisonRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = []
        for fund_id in serializer.validated_data["fund_ids"]:
            result = tools.get_mutual_fund_details(fund_id)
            if not result.get("success"):
                return _tool_result(result, {})
            fund = result["details"]
            rows.append({"fund_id": fund_id, "fund_name": fund["name"], "category": fund.get("category"), "return_3y": None, "risk_level": fund.get("riskometer"), "risk_adjusted_rating": None, "expense_ratio": fund.get("expense_ratio"), "fund_size": fund.get("aum_crore"), "manager_name": fund.get("fund_manager"), "manager_tenure_years": None, "as_of": fund.get("latest_portfolio_date")})
        return _success({"funds": rows}, [{"name": "Mock fund master", "data_as_of": date.today().isoformat()}])


class SipCalculatorView(APIView):
    @extend_schema(request=SipRequestSerializer, responses={200: ApiEnvelopeSerializer})
    def post(self, request):
        serializer = SipRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        monthly_rate = values["expected_annual_return"] / 100 / 12
        months = values["duration_years"] * 12
        monthly = values["monthly_investment"]
        wealth = monthly * months if monthly_rate == 0 else monthly * (((1 + monthly_rate) ** months - 1) / monthly_rate) * (1 + monthly_rate)
        total = monthly * months
        yearly = []
        for year in range(1, values["duration_years"] + 1):
            year_months = year * 12
            value = monthly * year_months if monthly_rate == 0 else monthly * (((1 + monthly_rate) ** year_months - 1) / monthly_rate) * (1 + monthly_rate)
            yearly.append({"year": year, "total_invested": round(monthly * year_months, 2), "expected_wealth": round(value, 2)})
        return _success({"total_invested": round(total, 2), "estimated_returns": round(wealth - total, 2), "expected_wealth": round(wealth, 2), "projection": True, "disclaimer": "This is an estimate based on the supplied annual return, not a guaranteed return.", "yearly_projection": yearly})


class ExpectedWealthCalculatorView(APIView):
    @extend_schema(request=ExpectedWealthRequestSerializer, responses={200: ApiEnvelopeSerializer})
    def post(self, request):
        serializer = ExpectedWealthRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        periods_per_year = 12 if values["frequency"] == "monthly" else 1
        periods = values["duration_years"] * periods_per_year
        rate = values["expected_annual_return"] / 100 / periods_per_year
        initial = values["initial_investment"]
        recurring = values["additional_investment"]
        growth_factor = (1 + rate) ** periods
        recurring_value = recurring * periods if rate == 0 else recurring * ((growth_factor - 1) / rate) * (1 + rate)
        wealth = initial * growth_factor + recurring_value
        contribution = initial + recurring * periods
        return _success({"total_contribution": round(contribution, 2), "estimated_growth": round(wealth - contribution, 2), "expected_wealth": round(wealth, 2), "projection": True, "disclaimer": "This is an estimate based on the supplied annual return, not a guaranteed return."})


class CompanyFundExposureView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={200: ApiEnvelopeSerializer})
    def get(self, request, company_id):
        user_id = _required_user_id(request)
        company = tools.store.companies().get(company_id)
        if not company:
            return Response({"success": False, "error_code": "COMPANY_NOT_FOUND", "message": "Company was not found."}, status=404)
        portfolio = tools.get_portfolio(user_id) if user_id else {"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}
        if not portfolio.get("success"):
            return _tool_result(portfolio, {})
        funds = []
        for position in portfolio["funds"]:
            holdings = tools.get_fund_holdings(position["fund_id"])
            item = next((entry for entry in holdings.get("holdings", []) if entry["company_id"] == company_id), None)
            if item:
                funds.append({"fund_id": position["fund_id"], "fund_name": position["fund_name"], "fund_exposure_percent": item["weight_percentage"], "in_user_portfolio": True})
        exposure = tools.calculate_exposure(user_id, company_id)
        return _tool_result(exposure, {"company": {"company_id": company_id, "name": company["name"], "sector": company["sector"]}, "funds_holding_company": funds, "user_portfolio_exposure_percent": exposure.get("exposures", [{}])[0].get("portfolio_weight_percentage", 0)})


class WatchlistView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={200: ApiEnvelopeSerializer})
    def get(self, request):
        user_id = _required_user_id(request)
        if not user_id:
            return Response({"success": False, "error_code": "INVALID_INPUT", "message": "user_id is required."}, status=400)
        items = []
        for item in WatchlistItem.objects.filter(user_id=user_id):
            company = tools.store.companies().get(item.symbol, {"name": item.symbol})
            market = tools.get_market_data(item.symbol)
            data = market.get("data", {}) if market.get("success") else {}
            items.append({"id": item.id, "symbol": item.symbol, "name": company["name"], "price": data.get("price"), "change_percent": data.get("price_change_percentage"), "as_of": data.get("timestamp")})
        return _success({"items": items})

    @extend_schema(request=WatchlistCreateSerializer, responses={201: ApiEnvelopeSerializer})
    def post(self, request):
        serializer = WatchlistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["symbol"] not in tools.store.companies():
            return Response({"success": False, "error_code": "COMPANY_NOT_FOUND", "message": "Only configured company IDs can be added to the watchlist."}, status=404)
        item, created = WatchlistItem.objects.get_or_create(**values)
        return _success(
            {"id": item.id, "symbol": item.symbol, "created": created},
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WatchlistItemView(APIView):
    @extend_schema(parameters=[OpenApiParameter("user_id", OpenApiTypes.STR, OpenApiParameter.QUERY, required=True)], responses={204: None, 404: ApiEnvelopeSerializer})
    def delete(self, request, item_id):
        user_id = _required_user_id(request)
        deleted, _ = WatchlistItem.objects.filter(id=item_id, user_id=user_id).delete()
        if not deleted:
            return Response({"success": False, "error_code": "WATCHLIST_ITEM_NOT_FOUND", "message": "Watchlist item was not found for this user."}, status=404)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotConfiguredView(GenericAPIView):
    capability = "This capability is not configured."
    serializer_class = ApiEnvelopeSerializer

    def _response(self):
        return Response({"success": False, "error_code": "DATA_NOT_CONFIGURED", "message": self.capability}, status=status.HTTP_501_NOT_IMPLEMENTED)

    @extend_schema(responses={501: ApiEnvelopeSerializer})
    def get(self, request, *args, **kwargs):
        return self._response()

    @extend_schema(responses={501: ApiEnvelopeSerializer})
    def post(self, request, *args, **kwargs):
        return self._response()
