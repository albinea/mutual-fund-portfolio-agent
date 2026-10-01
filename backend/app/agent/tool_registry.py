"""LLM-neutral registry, schema generation, validation, and execution."""
from __future__ import annotations

import inspect
from typing import Any, get_type_hints

from pydantic import ConfigDict, ValidationError, create_model

from ..tools.core import FUNCTIONS, DESCRIPTIONS
from ..schemas import ToolSpec

CATEGORY={
 "get_portfolio":"portfolio","get_fund_holdings":"portfolio","calculate_exposure":"portfolio","calculate_fund_overlap":"portfolio","calculate_sector_exposure":"portfolio","calculate_portfolio_risk":"portfolio",
 "search_financial_documents":"rag","get_mutual_fund_details":"rag","get_historical_performance":"rag",
 "web_search":"external","search_company_news":"external","get_market_data":"external","research_company":"external",
 "simulate_allocation":"analysis","compare_scenarios":"analysis","calculate_tax_impact":"analysis","analyze_goal":"analysis","validate_analysis":"analysis",
 "get_nav_history":"market_data","calculate_cagr":"market_data","calculate_volatility":"market_data","calculate_drawdown":"market_data","compare_funds":"market_data"}
TOOLS={fn.__name__:fn for fn in FUNCTIONS}

PORTFOLIO_SCOPED = {
    "get_portfolio", "get_fund_holdings", "calculate_exposure", "calculate_fund_overlap",
    "calculate_sector_exposure", "calculate_portfolio_risk", "simulate_allocation",
    "compare_scenarios", "calculate_tax_impact", "analyze_goal",
}

DESCRIPTIONS.update({
    "get_portfolio": "Retrieve the authenticated user's active statement, total invested value, current value, and fund positions.",
    "get_fund_holdings": "Retrieve a fund's uploaded disclosure holdings and disclosure date for the authenticated user's active imported portfolio.",
    "calculate_exposure": "Calculate the authenticated user's company or issuer exposure from matching uploaded fund disclosures. Results include fund_count and fund names: use fund_count for 'held by most funds' and percentage for 'highest exposure'.",
    "calculate_fund_overlap": "Calculate companies or issuers held through two or more funds in the authenticated user's active imported portfolio. Never infer overlap when a required fund disclosure is unavailable.",
    "calculate_sector_exposure": "Calculate sector exposure from matching uploaded disclosures for the authenticated user's active imported portfolio.",
    "calculate_portfolio_risk": "Calculate portfolio concentration and supplied historical-return risk metrics.",
    "search_financial_documents": "Search trusted internal factsheets and financial documents; use for historical/document questions.",
    "web_search": "Search current external information; use for latest or recent questions, not calculations.",
    "simulate_allocation": "Simulate one additional-investment allocation using the actual current portfolio.",
    "compare_scenarios": "Calculate and compare multiple allocation scenarios without declaring a best investment.",
    "validate_analysis": "Validate sourced claims and reject unsupported certainty before a complex final answer.",
})


def _input_model(fn: Any, hide_user_id: bool = False) -> type:
    signature = inspect.signature(fn)
    hints = get_type_hints(fn)
    fields: dict[str, tuple[Any, Any]] = {}
    for name, parameter in signature.parameters.items():
        # Provider objects are server-side dependency-injection seams, not tool inputs.
        if name == "provider" or (hide_user_id and name == "user_id"):
            continue
        annotation = hints.get(name, Any)
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        fields[name] = (annotation, default)
    return create_model(
        f"{fn.__name__.title().replace('_', '')}Input",
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )


def registry(for_model: bool = False, names: set[str] | None = None) -> list[dict[str, Any]]:
    result = []
    for fn in FUNCTIONS:
        if names is not None and fn.__name__ not in names:
            continue
        input_schema = _input_model(fn, hide_user_id=for_model).model_json_schema()
        input_schema.pop("title", None)
        result.append(ToolSpec(
            name=fn.__name__,
            description=DESCRIPTIONS[fn.__name__],
            input_schema=input_schema,
            output_schema={
                "type": "object",
                "properties": {"success": {"type": "boolean"}, "source": {"anyOf": [{"type": "object"}, {"type": "null"}]}},
                "additionalProperties": True,
            },
            category=CATEGORY[fn.__name__],
            required_permissions=["portfolio:read"] if fn.__name__ in PORTFOLIO_SCOPED else [],
        ).model_dump())
    return result


def call_tool(name: str, arguments: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
    """Validate a call and bind portfolio identity from trusted request context."""
    if name not in TOOLS:
        return {"success": False, "error_code": "UNKNOWN_TOOL", "message": "Tool is not registered.", "source": None}
    fn = TOOLS[name]
    supplied = dict(arguments or {})
    if "user_id" in inspect.signature(fn).parameters and user_id is not None:
        supplied.pop("user_id", None)
        supplied["user_id"] = user_id
    try:
        model = _input_model(fn)
        validated = model.model_validate(supplied).model_dump()
        return fn(**validated)
    except ValidationError as exc:
        return {"success": False, "error_code": "INVALID_INPUT", "message": str(exc), "source": None}
    except (TypeError, ValueError) as exc:
        return {"success": False, "error_code": "INVALID_INPUT", "message": str(exc), "source": None}
    except Exception:
        return {"success": False, "error_code": "TOOL_FAILURE", "message": "Tool could not complete the request.", "source": None}
