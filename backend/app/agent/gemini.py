"""Optional Gemini orchestration over the registered portfolio tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .tool_registry import call_tool

try:
    from google import genai
    from google.genai import types
except ImportError:  # Keeps the core FastAPI tools usable if the optional SDK is absent.
    genai = None
    types = None

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def answer_question(question: str, user_id: str) -> dict[str, Any]:
    """Answer a question with Gemini, restricting portfolio reads to ``user_id``."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "success": False,
            "error_code": "GEMINI_NOT_CONFIGURED",
            "message": "Set GEMINI_API_KEY before using the agent endpoint.",
            "source": None,
        }
    if genai is None or types is None:
        return {
            "success": False,
            "error_code": "GEMINI_SDK_UNAVAILABLE",
            "message": "Install the google-genai package before using the agent endpoint.",
            "source": None,
        }

    # Portfolio functions deliberately take no user ID. The API route owns identity
    # until real authentication replaces this demonstration parameter.
    def get_my_portfolio() -> dict:
        """Retrieve the authenticated user's portfolio summary."""
        return call_tool("get_portfolio", {"user_id": user_id})

    def get_my_portfolio_risk() -> dict:
        """Retrieve concentration and historical risk metrics for the user's portfolio."""
        return call_tool("calculate_portfolio_risk", {"user_id": user_id})

    def get_my_sector_exposure() -> dict:
        """Retrieve the user's sector exposure across all portfolio funds."""
        return call_tool("calculate_sector_exposure", {"user_id": user_id})

    def get_my_fund_overlap() -> dict:
        """Retrieve companies held through more than one fund in the user's portfolio."""
        return call_tool("calculate_fund_overlap", {"user_id": user_id})

    def calculate_nav_cagr(scheme_code: int, years: int) -> dict:
        """Calculate public mutual-fund NAV CAGR for a scheme code and number of years."""
        return call_tool("calculate_cagr", {"scheme_code": scheme_code, "years": years})

    def calculate_nav_volatility(scheme_code: int, years: int) -> dict:
        """Calculate annualized NAV volatility for a scheme code and number of years."""
        return call_tool("calculate_volatility", {"scheme_code": scheme_code, "years": years})

    def calculate_nav_drawdown(scheme_code: int, years: int) -> dict:
        """Calculate maximum NAV drawdown for a scheme code and number of years."""
        return call_tool("calculate_drawdown", {"scheme_code": scheme_code, "years": years})

    def compare_nav_funds(scheme_codes: list[int], years: int) -> dict:
        """Compare public NAV CAGR, volatility, and maximum drawdown across scheme codes."""
        return call_tool("compare_funds", {"scheme_codes": scheme_codes, "years": years})

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=question,
            config=types.GenerateContentConfig(
                tools=[
                    get_my_portfolio,
                    get_my_portfolio_risk,
                    get_my_sector_exposure,
                    get_my_fund_overlap,
                    calculate_nav_cagr,
                    calculate_nav_volatility,
                    calculate_nav_drawdown,
                    compare_nav_funds,
                ]
            ),
        )
        return {
            "success": True,
            "answer": response.text,
            "source": {"name": "Gemini orchestration"},
        }
    except Exception:
        # Do not return provider internals or prompt data in an API error.
        return {
            "success": False,
            "error_code": "AGENT_FAILURE",
            "message": "The agent could not complete the request.",
            "source": None,
        }
