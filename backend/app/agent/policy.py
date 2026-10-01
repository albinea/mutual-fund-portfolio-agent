"""Small routing guardrail that gives the model only relevant existing tools."""
from __future__ import annotations


class ToolSelectionPolicy:
    """Classify broad intent without performing analysis or calculations."""

    PORTFOLIO = {"get_portfolio"}
    HOLDINGS = {"get_fund_holdings", "get_mutual_fund_details"}
    CURRENT = {"web_search", "search_company_news", "get_market_data", "research_company"}
    NAV = {"get_nav_history", "calculate_cagr", "calculate_volatility", "calculate_drawdown", "compare_funds"}

    def select(self, question: str, available: set[str]) -> set[str]:
        q = question.casefold()
        selected: set[str] = set()

        scenario = any(term in q for term in ("scenario", "allocate", "allocation", "more to invest", "additional invest"))
        current = any(term in q for term in ("latest", "today", "recent", "currently", "this week", "this month", "what happened", "news", "current price", "happening"))
        factsheet = any(term in q for term in ("factsheet", "annual report", "document", "disclosure"))
        company = any(term in q for term in ("compan", "indirect", "underlying"))
        portfolio = any(term in q for term in ("my ", "portfolio", "i own", "i invested", "invested", "exposure"))
        fund = any(term in q for term in ("fund", "scheme", "holding", "invest in"))

        if any(term in q for term in ("scheme code", "nav", "cagr", "drawdown", "volatility", "historical return")):
            selected |= self.NAV
        if scenario:
            selected |= self.PORTFOLIO | self.HOLDINGS | {
                "calculate_exposure",
                "calculate_sector_exposure",
                "calculate_fund_overlap",
                "calculate_portfolio_risk",
                "simulate_allocation",
                "compare_scenarios",
                "validate_analysis",
            }
        elif "overlap" in q or "duplicate" in q:
            selected |= self.PORTFOLIO | {"get_fund_holdings", "calculate_fund_overlap"}
        elif "sector" in q:
            selected |= self.PORTFOLIO | {"get_fund_holdings", "calculate_sector_exposure"}
        elif any(term in q for term in ("risk", "concentration", "sharpe")):
            selected |= self.PORTFOLIO | {"calculate_portfolio_risk"}
        elif company and portfolio:
            selected |= self.PORTFOLIO | {"get_fund_holdings", "calculate_exposure"}
        elif portfolio:
            selected |= self.PORTFOLIO
        if fund and not selected:
            selected |= self.HOLDINGS
        if factsheet:
            selected |= self.HOLDINGS | {"search_financial_documents"}
        if any(term in q for term in ("historical performance", "past performance", "performance history")):
            selected |= {"get_historical_performance", "get_mutual_fund_details"}
        if current:
            selected |= self.CURRENT | {"validate_analysis"}
            if portfolio:
                selected |= self.PORTFOLIO | {"get_fund_holdings", "calculate_exposure"}
        if any(term in q for term in ("tax", "redemption", "capital gain")):
            selected |= self.PORTFOLIO | {"calculate_tax_impact", "validate_analysis"}
        if any(term in q for term in ("goal", "target amount", "horizon")):
            selected |= self.PORTFOLIO | {"analyze_goal", "validate_analysis"}

        # Ambiguous questions remain flexible. Clear simple questions stay narrow.
        return (selected or available) & available
