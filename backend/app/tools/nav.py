"""Live NAV analytics backed by the public MF API.

These tools keep the calculations from the standalone MF agent but return the
same structured result and provenance shape as the portfolio tools.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests


MF_API = "https://api.mfapi.in/mf"
SEARCH_CACHE_TTL_SECONDS = 60 * 60
LATEST_CACHE_TTL_SECONDS = 5 * 60
NAV_CACHE_TTL_SECONDS = 15 * 60
_search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_latest_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_nav_cache: dict[int, tuple[float, pd.DataFrame, dict[str, Any]]] = {}


def _source(
    scheme_code: int,
    data_as_of: str | None = None,
    *,
    scheme_name: str | None = None,
    endpoint: str | None = None,
) -> dict[str, Any]:
    return {
        "name": f"{scheme_name} NAV via MFapi.in" if scheme_name else "MFapi.in NAV data",
        "url": endpoint or f"{MF_API}/{scheme_code}",
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "data_as_of": data_as_of,
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "message": message, "source": None}


def _provider_error(exc: requests.RequestException) -> dict[str, Any]:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return _error("RATE_LIMITED", "MFapi.in is rate limiting requests. Please try again shortly.")
    if status == 404:
        return _error("DATA_UNAVAILABLE", "MFapi.in has no data for that scheme or date.")
    return _error("PROVIDER_UNAVAILABLE", "MFapi.in could not be reached. Please try again shortly.")


def _parse_nav_frame(rows: Any) -> pd.DataFrame:
    if not isinstance(rows, list) or not rows:
        raise ValueError("No NAV history is available for this scheme.")
    frame = pd.DataFrame(rows)
    if not {"date", "nav"}.issubset(frame.columns):
        raise ValueError("The NAV provider returned an invalid data shape.")
    frame["date"] = pd.to_datetime(frame["date"], format="%d-%m-%Y", errors="coerce")
    frame["nav"] = pd.to_numeric(frame["nav"], errors="coerce")
    frame = frame.dropna(subset=["date", "nav"])
    frame = frame[frame["nav"] > 0].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("The NAV provider did not return usable observations.")
    return frame


def _search_schemes(query: str) -> list[dict[str, Any]]:
    normalized = " ".join(query.casefold().split())
    cached = _search_cache.get(normalized)
    if cached and time.monotonic() - cached[0] < SEARCH_CACHE_TTL_SECONDS:
        return cached[1]

    response = requests.get(f"{MF_API}/search", params={"q": query}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("results", []))
    if not isinstance(payload, list):
        raise ValueError("MFapi.in returned an invalid scheme search response.")

    schemes = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = item.get("schemeCode", item.get("scheme_code"))
        name = item.get("schemeName", item.get("scheme_name"))
        try:
            code = int(code)
        except (TypeError, ValueError):
            continue
        if code > 0 and isinstance(name, str) and name.strip():
            schemes.append({"scheme_code": code, "scheme_name": name.strip()})
    # Avoid retaining an unbounded cache if many different queries arrive.
    if len(_search_cache) > 256:
        _search_cache.clear()
    _search_cache[normalized] = (time.monotonic(), schemes)
    return schemes


def _scheme_base(name: str) -> str:
    """Remove plan/option suffixes so variants can be compared as one family."""
    value = name.casefold().replace("&", " and ")
    value = re.sub(r"\b(direct|regular)\s+plan\b", " ", value)
    value = re.sub(
        r"(?:\s*[-–]\s*|\s+)(?:growth(?:\s+option)?|idcw(?:\s+(?:payout|reinvestment|option))?|"
        r"dividend(?:\s+(?:payout|reinvestment|option))?|bonus(?:\s+option)?|"
        r"reinvestment|payout|payment)\s*$",
        " ",
        value,
    )
    value = re.sub(r"\b(option|plan)\b", " ", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _scheme_variant(name: str) -> tuple[str | None, str | None]:
    value = name.casefold()
    plan = "direct" if re.search(r"\bdirect\s+plan\b", value) else "regular" if re.search(r"\bregular\s+plan\b", value) else None
    if re.search(r"\bidcw(?:\s+(?:payout|reinvestment|option))?\s*$|\bdividend\s+(?:payout|reinvestment|option)\s*$", value):
        option = "idcw"
    elif re.search(r"\bbonus(?:\s+option)?\s*$", value):
        option = "bonus"
    elif re.search(r"\bgrowth(?:\s+option)?\s*$", value):
        option = "growth"
    else:
        option = None
    return plan, option


def _resolve_scheme(fund_name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve only a unique exact fund family/variant; never silently choose a plan."""
    query = " ".join(fund_name.split())
    if not query:
        return None, _error("INVALID_INPUT", "fund_name must not be empty.")
    try:
        schemes = _search_schemes(query)
    except requests.RequestException as exc:
        return None, _provider_error(exc)
    except ValueError:
        return None, _error("PROVIDER_UNAVAILABLE", "MFapi.in returned an invalid scheme search response.")

    family = _scheme_base(query)
    candidates = [item for item in schemes if _scheme_base(item["scheme_name"]) == family]
    requested_plan, requested_option = _scheme_variant(query)
    if requested_plan:
        candidates = [item for item in candidates if _scheme_variant(item["scheme_name"])[0] == requested_plan]
    if requested_option:
        candidates = [item for item in candidates if _scheme_variant(item["scheme_name"])[1] == requested_option]

    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        # Give the agent (and user) the actual choices, not an arbitrary first result.
        return None, {
            **_error("FUND_AMBIGUOUS", "Several plan/option variants match. Specify the exact plan and option."),
            "candidates": candidates[:12],
        }
    return None, _error("FUND_NOT_FOUND", "No exact MFapi.in scheme match was found. Check the fund name and plan.")


def search_mutual_fund_schemes(query: str, limit: int = 10) -> dict[str, Any]:
    """Search MFapi.in for Indian mutual-fund schemes and return their exact plan names/codes."""
    try:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty.")
        if len(query) > 200:
            raise ValueError("query must be 200 characters or fewer.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit must be an integer between 1 and 20.")
        schemes = _search_schemes(query.strip())
        source = {
            "name": "MFapi.in scheme search",
            "url": f"{MF_API}/search?{urlencode({'q': query.strip()})}",
            "retrieved_at": datetime.utcnow().isoformat() + "Z",
            "data_as_of": None,
        }
        return {"success": True, "query": query.strip(), "schemes": schemes[:limit], "source": source}
    except requests.RequestException as exc:
        return _provider_error(exc)
    except ValueError as exc:
        return _error("INVALID_INPUT", str(exc))


def _get_latest_payload(scheme_code: int) -> dict[str, Any]:
    cached = _latest_cache.get(scheme_code)
    if cached and time.monotonic() - cached[0] < LATEST_CACHE_TTL_SECONDS:
        return cached[1]
    response = requests.get(f"{MF_API}/{scheme_code}/latest", timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("MFapi.in returned an invalid latest-NAV response.")
    if len(_latest_cache) > 256:
        _latest_cache.clear()
    _latest_cache[scheme_code] = (time.monotonic(), payload)
    return payload


def get_mutual_fund_nav(fund_name: str, nav_date: str | None = None) -> dict[str, Any]:
    """Get a named scheme's latest NAV or its NAV on/just before a requested date."""
    if len(fund_name) > 200:
        return _error("INVALID_INPUT", "fund_name must be 200 characters or fewer.")
    requested = None
    if nav_date is not None:
        try:
            requested = date.fromisoformat(nav_date)
        except (TypeError, ValueError):
            return _error("INVALID_INPUT", "nav_date must use YYYY-MM-DD format.")
    scheme, error = _resolve_scheme(fund_name)
    if error:
        return error
    assert scheme is not None
    code = scheme["scheme_code"]
    try:
        if nav_date is None:
            payload = _get_latest_payload(code)
            frame = _parse_nav_frame(payload.get("data"))
            endpoint = f"{MF_API}/{code}/latest"
            row = frame.iloc[-1]
        else:
            assert requested is not None
            params = {
                "startDate": (requested - timedelta(days=10)).isoformat(),
                "endDate": requested.isoformat(),
            }
            response = requests.get(f"{MF_API}/{code}", params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            frame = _parse_nav_frame(payload.get("data") if isinstance(payload, dict) else None)
            frame = frame[frame["date"].dt.date <= requested]
            if frame.empty:
                return _error("DATA_UNAVAILABLE", f"No NAV was found on or before {requested.isoformat()}.")
            endpoint = f"{MF_API}/{code}?{urlencode(params)}"
            row = frame.iloc[-1]
        source = _source(code, row["date"].date().isoformat(), scheme_name=scheme["scheme_name"], endpoint=endpoint)
        return {
            "success": True,
            "scheme_code": code,
            "scheme_name": scheme["scheme_name"],
            "currency": "INR",
            "requested_date": nav_date,
            "nav": round(float(row["nav"]), 4),
            "nav_date": row["date"].date().isoformat(),
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError) as exc:
        return _error("DATA_UNAVAILABLE", str(exc))


def _nav_history(scheme_code: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(scheme_code, int) or isinstance(scheme_code, bool) or scheme_code <= 0:
        raise ValueError("scheme_code must be a positive integer.")

    cached = _nav_cache.get(scheme_code)
    if cached and time.monotonic() - cached[0] < NAV_CACHE_TTL_SECONDS:
        return cached[1].copy(), cached[2]

    response = requests.get(f"{MF_API}/{scheme_code}", timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("The NAV provider returned an invalid data shape.")
    frame = _parse_nav_frame(payload.get("data"))
    scheme_name = (payload.get("meta") or {}).get("scheme_name")
    source = _source(scheme_code, frame.iloc[-1]["date"].date().isoformat(), scheme_name=scheme_name)
    if len(_nav_cache) > 256:
        _nav_cache.clear()
    _nav_cache[scheme_code] = (time.monotonic(), frame.copy(), source)
    return frame, source


def calculate_lump_sum_value(
    fund_name: str,
    principal: float = 10000,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Estimate one-time NAV growth from the earliest available observation or a chosen start date."""
    if len(fund_name) > 200:
        return _error("INVALID_INPUT", "fund_name must be 200 characters or fewer.")
    if isinstance(principal, bool) or not isinstance(principal, (int, float)) or principal <= 0:
        return _error("INVALID_INPUT", "principal must be a positive amount.")
    try:
        start_limit = date.fromisoformat(start_date) if start_date else None
        end_limit = date.fromisoformat(end_date) if end_date else None
    except (TypeError, ValueError):
        return _error("INVALID_INPUT", "start_date and end_date must use YYYY-MM-DD format.")
    if start_limit and end_limit and start_limit > end_limit:
        return _error("INVALID_INPUT", "start_date must be on or before end_date.")
    scheme, error = _resolve_scheme(fund_name)
    if error:
        return error
    assert scheme is not None
    try:
        frame, _ = _nav_history(scheme["scheme_code"])
        latest_available_date = frame["date"].iloc[-1].date()
        if start_limit and start_limit > latest_available_date:
            raise ValueError("start_date is later than MFapi.in's latest available NAV.")
        if start_limit:
            eligible_start = frame[frame["date"].dt.date <= start_limit]
        else:
            eligible_start = frame
        if end_limit:
            eligible_end = frame[frame["date"].dt.date <= end_limit]
        else:
            eligible_end = frame
        if eligible_start.empty or eligible_end.empty:
            raise ValueError("The requested date range has no available NAV observations.")
        first = eligible_start.iloc[0] if start_limit is None else eligible_start.iloc[-1]
        last = eligible_end.iloc[-1]
        if first["date"] > last["date"]:
            raise ValueError("No NAV observations are available between the requested dates.")
        value = float(principal) * float(last["nav"]) / float(first["nav"])
        total_return = (float(last["nav"]) / float(first["nav"]) - 1) * 100
        endpoint = f"{MF_API}/{scheme['scheme_code']}"
        source = _source(
            scheme["scheme_code"],
            last["date"].date().isoformat(),
            scheme_name=scheme["scheme_name"],
            endpoint=endpoint,
        )
        return {
            "success": True,
            "scheme_code": scheme["scheme_code"],
            "scheme_name": scheme["scheme_name"],
            "currency": "INR",
            "principal": round(float(principal), 2),
            "estimated_value": round(value, 2),
            "total_return_percent": round(total_return, 2),
            "start_date": first["date"].date().isoformat(),
            "start_nav": round(float(first["nav"]), 6),
            "end_date": last["date"].date().isoformat(),
            "end_nav": round(float(last["nav"]), 6),
            "start_basis": "earliest_available_nav" if start_limit is None else "latest_nav_on_or_before_requested_start_date",
            "methodology": "One-time investment value estimated by principal × end NAV ÷ start NAV. With no start date, the calculation starts at the earliest NAV observation available from MFapi.in; that date may not equal the scheme's legal inception. This is not an SIP or benchmark calculation. It excludes taxes, exit loads, and any IDCW distributions paid outside NAV; for IDCW plans it is not the investor's total value/return.",
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        return _error("DATA_UNAVAILABLE", str(exc))


def _window(frame: pd.DataFrame, years: int) -> tuple[pd.Series, pd.DataFrame]:
    if not isinstance(years, int) or isinstance(years, bool) or years <= 0:
        raise ValueError("years must be a positive integer.")
    end = frame.iloc[-1]
    start_date = end["date"] - pd.DateOffset(years=years)
    possible_starts = frame[frame["date"] <= start_date]
    period = frame[frame["date"] >= start_date].copy()
    if possible_starts.empty or len(period) < 2:
        raise ValueError(f"Not enough data to calculate {years}-year metrics.")
    return possible_starts.iloc[-1], period


def get_nav_history(scheme_code: int, limit: int = 30) -> dict[str, Any]:
    """Return recent public NAV observations for an Indian mutual-fund scheme."""
    try:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 365:
            raise ValueError("limit must be an integer between 1 and 365.")
        frame, source = _nav_history(scheme_code)
        observations = [
            {"date": row.date.date().isoformat(), "nav": round(float(row.nav), 4)}
            for row in frame.tail(limit).itertuples(index=False)
        ]
        return {
            "success": True,
            "scheme_code": scheme_code,
            "observations": observations,
            "total_observations": len(frame),
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError) as exc:
        return _error("INVALID_INPUT", str(exc))


def calculate_cagr(scheme_code: int, years: int) -> dict[str, Any]:
    """Calculate annualized NAV return (CAGR) for a public scheme code."""
    try:
        frame, source = _nav_history(scheme_code)
        start, _ = _window(frame, years)
        end = frame.iloc[-1]
        value = ((end["nav"] / start["nav"]) ** (1 / years) - 1) * 100
        return {
            "success": True,
            "scheme_code": scheme_code,
            "years": years,
            "cagr_percent": round(float(value), 2),
            "start_date": start["date"].date().isoformat(),
            "end_date": end["date"].date().isoformat(),
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        return _error("INVALID_INPUT", str(exc))


def calculate_volatility(scheme_code: int, years: int) -> dict[str, Any]:
    """Calculate annualized daily NAV volatility for a public scheme code."""
    try:
        frame, source = _nav_history(scheme_code)
        _, period = _window(frame, years)
        daily_returns = period["nav"].pct_change().dropna()
        if len(daily_returns) < 2:
            raise ValueError(f"Not enough data to calculate {years}-year volatility.")
        value = daily_returns.std() * (252**0.5) * 100
        return {
            "success": True,
            "scheme_code": scheme_code,
            "years": years,
            "annualized_volatility_percent": round(float(value), 2),
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError) as exc:
        return _error("INVALID_INPUT", str(exc))


def calculate_drawdown(scheme_code: int, years: int) -> dict[str, Any]:
    """Calculate maximum NAV drawdown for a public scheme code."""
    try:
        frame, source = _nav_history(scheme_code)
        _, period = _window(frame, years)
        drawdown = period["nav"] / period["nav"].cummax() - 1
        return {
            "success": True,
            "scheme_code": scheme_code,
            "years": years,
            "maximum_drawdown_percent": round(float(drawdown.min() * 100), 2),
            "source": source,
        }
    except requests.RequestException as exc:
        return _provider_error(exc)
    except (ValueError, TypeError) as exc:
        return _error("INVALID_INPUT", str(exc))


def compare_funds(scheme_codes: list[int], years: int) -> dict[str, Any]:
    """Compare public NAV CAGR, volatility, and maximum drawdown across schemes."""
    if not isinstance(scheme_codes, list) or len(scheme_codes) < 2:
        return _error("INVALID_INPUT", "scheme_codes must contain at least two scheme codes.")

    results = []
    for scheme_code in scheme_codes:
        try:
            frame, source = _nav_history(scheme_code)
            start, period = _window(frame, years)
            end = frame.iloc[-1]
            daily_returns = period["nav"].pct_change().dropna()
            if len(daily_returns) < 2:
                raise ValueError(f"Not enough data to calculate {years}-year volatility.")
            results.append(
                {
                    "scheme_code": scheme_code,
                    "cagr_percent": round(float(((end["nav"] / start["nav"]) ** (1 / years) - 1) * 100), 2),
                    "annualized_volatility_percent": round(float(daily_returns.std() * (252**0.5) * 100), 2),
                    "maximum_drawdown_percent": round(float((period["nav"] / period["nav"].cummax() - 1).min() * 100), 2),
                    "start_date": start["date"].date().isoformat(),
                    "end_date": end["date"].date().isoformat(),
                    "source": source,
                }
            )
        except requests.RequestException as exc:
            return {**_provider_error(exc), "scheme_code": scheme_code}
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            return {**_error("INVALID_INPUT", str(exc)), "scheme_code": scheme_code}
    return {
        "success": True,
        "years": years,
        "funds": results,
        "sources": [item["source"] for item in results],
        "source": {"name": "MFapi.in NAV history"},
    }
