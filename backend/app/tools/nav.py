"""Live NAV analytics backed by the public MF API.

These tools keep the calculations from the standalone MF agent but return the
same structured result and provenance shape as the portfolio tools.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import requests


MF_API = "https://api.mfapi.in/mf"


def _source(scheme_code: int, data_as_of: str | None = None) -> dict[str, Any]:
    return {
        "name": "MF API NAV history",
        "url": f"{MF_API}/{scheme_code}",
        "retrieved_at": datetime.utcnow().isoformat() + "Z",
        "data_as_of": data_as_of,
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "message": message, "source": None}


def _nav_history(scheme_code: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(scheme_code, int) or isinstance(scheme_code, bool) or scheme_code <= 0:
        raise ValueError("scheme_code must be a positive integer.")

    response = requests.get(f"{MF_API}/{scheme_code}", timeout=20)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("No NAV history is available for this scheme code.")

    frame = pd.DataFrame(rows)
    if not {"date", "nav"}.issubset(frame.columns):
        raise ValueError("The NAV provider returned an invalid data shape.")
    frame["date"] = pd.to_datetime(frame["date"], format="%d-%m-%Y", errors="coerce")
    frame["nav"] = pd.to_numeric(frame["nav"], errors="coerce")
    frame = frame.dropna(subset=["date", "nav"]).sort_values("date").reset_index(drop=True)
    if frame.empty:
        raise ValueError("The NAV provider did not return usable observations.")
    return frame, _source(scheme_code, frame.iloc[-1]["date"].date().isoformat())


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
    except requests.RequestException:
        return _error("PROVIDER_UNAVAILABLE", "The MF API could not be reached.")
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
    except requests.RequestException:
        return _error("PROVIDER_UNAVAILABLE", "The MF API could not be reached.")
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
    except requests.RequestException:
        return _error("PROVIDER_UNAVAILABLE", "The MF API could not be reached.")
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
    except requests.RequestException:
        return _error("PROVIDER_UNAVAILABLE", "The MF API could not be reached.")
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
                    "source": source,
                }
            )
        except requests.RequestException:
            return {**_error("PROVIDER_UNAVAILABLE", "The MF API could not be reached."), "scheme_code": scheme_code}
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            return {**_error("INVALID_INPUT", str(exc)), "scheme_code": scheme_code}
    return {"success": True, "years": years, "funds": results, "source": {"name": "MF API NAV history"}}
