"""Portfolio API data adapter: latest imported statement first, mock data as fallback."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.tools import core as tools
from django.db.models import Count

from .importing import normalize_fund_name
from .models import FundDisclosureHolding, FundDisclosureImport, PortfolioImport


class ImportedDisclosureUnavailable(ValueError):
    """Raised when a portfolio import cannot be safely matched to disclosure data."""


def active_import_for_user(user_id: str) -> PortfolioImport | None:
    return (
        PortfolioImport.objects.filter(user_id=user_id, is_active=True)
        .prefetch_related("holdings")
        .first()
    )


def get_portfolio_data(user_id: str) -> dict[str, Any]:
    """Return API-normalized positions from an import, or the existing development store."""

    portfolio_import = active_import_for_user(user_id)
    if portfolio_import is None:
        return tools.get_portfolio(user_id)

    holdings = list(portfolio_import.holdings.all())
    total_current = sum((holding.current_value for holding in holdings), Decimal("0"))
    total_invested = sum((holding.invested_amount for holding in holdings), Decimal("0"))
    funds = [
        {
            "fund_id": f"import-{holding.id}",
            "fund_name": holding.fund_name,
            "category": holding.category,
            "units": float(holding.units),
            "invested_amount": float(holding.invested_amount),
            "current_value": float(holding.current_value),
            "allocation_percentage": round(float(holding.current_value / total_current * 100), 4)
            if total_current
            else 0,
        }
        for holding in holdings
    ]
    return {
        "success": True,
        "user_id": user_id,
        "total_invested": float(total_invested),
        "current_value": float(total_current),
        "funds": funds,
        "imported": True,
        "source": {
            "name": f"Imported {portfolio_import.source_format.upper()} statement",
            "data_as_of": portfolio_import.snapshot_date.isoformat(),
        },
    }


def list_portfolio_snapshots(user_id: str) -> list[dict[str, Any]]:
    snapshots = (
        PortfolioImport.objects.filter(user_id=user_id)
        .annotate(holding_count=Count("holdings"))
        .order_by("-snapshot_date", "-imported_at")
    )
    return [
        {
            "id": snapshot.id,
            "snapshot_date": snapshot.snapshot_date,
            "source_file_name": snapshot.source_file_name,
            "source_format": snapshot.source_format,
            "holding_count": snapshot.holding_count,
            "is_active": snapshot.is_active,
        }
        for snapshot in snapshots
    ]


def _change_snapshot_for_user(user_id: str, snapshot_id: int) -> PortfolioImport | None:
    return PortfolioImport.objects.filter(user_id=user_id, id=snapshot_id).prefetch_related("holdings").first()


def compare_portfolio_snapshots(
    *,
    user_id: str,
    newer_snapshot_id: int | None = None,
    older_snapshot_id: int | None = None,
) -> dict[str, Any]:
    summaries = list_portfolio_snapshots(user_id)
    if len(summaries) < 2:
        return {"available": False, "snapshots": summaries, "changes": []}
    if (newer_snapshot_id is None) != (older_snapshot_id is None):
        raise ValueError("Select both an older and a newer snapshot.")
    if newer_snapshot_id is None:
        newer_snapshot_id, older_snapshot_id = summaries[0]["id"], summaries[1]["id"]
    if newer_snapshot_id == older_snapshot_id:
        raise ValueError("Select two different snapshots.")
    newer = _change_snapshot_for_user(user_id, newer_snapshot_id)
    older = _change_snapshot_for_user(user_id, older_snapshot_id)
    if newer is None or older is None:
        raise LookupError("One or both snapshots were not found for this user.")

    def rows(snapshot: PortfolioImport) -> dict[str, Any]:
        return {holding.fund_name.casefold(): holding for holding in snapshot.holdings.all()}

    newer_rows, older_rows = rows(newer), rows(older)
    changes: list[dict[str, Any]] = []
    for key in sorted(newer_rows.keys() | older_rows.keys()):
        current, previous = newer_rows.get(key), older_rows.get(key)
        if previous is None:
            change_type = "Added"
            value_change = current.current_value
            invested_change = current.invested_amount
            fund_name = current.fund_name
        elif current is None:
            change_type = "Removed"
            value_change = -previous.current_value
            invested_change = -previous.invested_amount
            fund_name = previous.fund_name
        else:
            value_change = current.current_value - previous.current_value
            invested_change = current.invested_amount - previous.invested_amount
            if value_change == 0 and invested_change == 0:
                continue
            change_type = "Increased" if value_change >= 0 else "Decreased"
            fund_name = current.fund_name
        changes.append(
            {
                "change_type": change_type,
                "fund_name": fund_name,
                "current_value_change": float(value_change),
                "invested_amount_change": float(invested_change),
                "newer_current_value": float(current.current_value) if current else 0,
                "older_current_value": float(previous.current_value) if previous else 0,
            }
        )
    return {
        "available": True,
        "snapshots": summaries,
        "newer_snapshot": {
            "id": newer.id,
            "snapshot_date": newer.snapshot_date,
            "source_file_name": newer.source_file_name,
        },
        "older_snapshot": {
            "id": older.id,
            "snapshot_date": older.snapshot_date,
            "source_file_name": older.source_file_name,
        },
        "changes": changes,
    }


def _latest_disclosures_for_funds(fund_names: list[str]) -> dict[str, FundDisclosureImport]:
    """Select the latest manually uploaded disclosure snapshot for each normalized fund name."""

    normalized_names = {normalize_fund_name(name) for name in fund_names}
    candidates = (
        FundDisclosureHolding.objects.filter(normalized_fund_name__in=normalized_names)
        .select_related("disclosure_import")
        .order_by("normalized_fund_name", "-disclosure_import__disclosure_date", "-disclosure_import__id")
    )
    latest: dict[str, FundDisclosureImport] = {}
    for candidate in candidates:
        latest.setdefault(candidate.normalized_fund_name, candidate.disclosure_import)
    return latest


def imported_disclosure_exposure(user_id: str) -> dict[str, Any]:
    """Calculate company and sector exposure from a statement plus matching disclosure uploads."""

    portfolio = get_portfolio_data(user_id)
    if not portfolio.get("imported"):
        raise ImportedDisclosureUnavailable("Import a portfolio statement before calculating disclosure-based overlap.")
    funds = portfolio["funds"]
    latest_disclosures = _latest_disclosures_for_funds([fund["fund_name"] for fund in funds])
    unmatched = [
        fund["fund_name"]
        for fund in funds
        if normalize_fund_name(fund["fund_name"]) not in latest_disclosures
    ]
    if unmatched:
        names = ", ".join(unmatched)
        raise ImportedDisclosureUnavailable(
            "Company holdings are missing for: "
            f"{names}. Upload a disclosure CSV/XLSX containing these fund names before calculating overlap."
        )

    total_current = Decimal(str(portfolio["current_value"]))
    if total_current <= 0:
        raise ImportedDisclosureUnavailable("The active portfolio has no current value to use for exposure calculations.")

    companies: dict[str, dict[str, Any]] = {}
    sectors: dict[str, Decimal] = {}
    source_imports: dict[int, FundDisclosureImport] = {}
    for fund in funds:
        normalized_name = normalize_fund_name(fund["fund_name"])
        disclosure_import = latest_disclosures[normalized_name]
        source_imports[disclosure_import.id] = disclosure_import
        fund_value = Decimal(str(fund["current_value"]))
        disclosure_rows = FundDisclosureHolding.objects.filter(
            disclosure_import=disclosure_import,
            normalized_fund_name=normalized_name,
        )
        for holding in disclosure_rows:
            contribution = fund_value / total_current * holding.holding_weight
            company_key = holding.isin or f"name:{holding.company_name.casefold()}"
            company = companies.setdefault(
                company_key,
                {
                    "company": holding.company_name,
                    "isin": holding.isin or None,
                    "sector": holding.sector or "Unclassified",
                    "portfolio_exposure_percent": Decimal("0"),
                    "funds": [],
                },
            )
            company["portfolio_exposure_percent"] += contribution
            company["funds"].append(
                {
                    "fund_name": fund["fund_name"],
                    "fund_holding_percent": float(holding.holding_weight),
                    "portfolio_contribution_percent": round(float(contribution), 4),
                }
            )
            sector = holding.sector or "Unclassified"
            sectors[sector] = sectors.get(sector, Decimal("0")) + contribution

    source_rows = [
        {
            "name": disclosure.source_name,
            "url": disclosure.source_url or None,
            "data_as_of": disclosure.disclosure_date.isoformat(),
        }
        for disclosure in source_imports.values()
    ]
    company_rows = [
        {
            **company,
            "portfolio_exposure_percent": round(float(company["portfolio_exposure_percent"]), 4),
        }
        for company in companies.values()
    ]
    company_rows.sort(key=lambda row: row["portfolio_exposure_percent"], reverse=True)
    sector_rows = [
        {
            "name": sector,
            "percentage": round(float(exposure), 4),
            "value": round(float(total_current * exposure / 100), 2),
            "funds": [],
        }
        for sector, exposure in sectors.items()
    ]
    sector_rows.sort(key=lambda row: row["percentage"], reverse=True)
    return {
        "companies": company_rows,
        "sectors": sector_rows,
        "sources": source_rows,
        "portfolio_as_of": portfolio["source"].get("data_as_of"),
    }


def calculate_imported_overlap(user_id: str) -> dict[str, Any]:
    """Return only companies held through two or more funds in an imported portfolio."""

    exposure = imported_disclosure_exposure(user_id)
    companies = [company for company in exposure["companies"] if len(company["funds"]) > 1]
    overall_overlap = sum(
        (Decimal(str(company["portfolio_exposure_percent"])) for company in companies),
        Decimal("0"),
    )
    return {
        **exposure,
        "companies": companies,
        "overall_overlap_percent": round(float(overall_overlap), 4),
    }
