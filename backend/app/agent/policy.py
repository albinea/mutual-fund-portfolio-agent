"""Small routing guardrail that gives the model only relevant existing tools."""
from __future__ import annotations


class ToolSelectionPolicy:
    """Classify broad intent without performing analysis or calculations."""

    PORTFOLIO = {"get_portfolio"}
    HOLDINGS = {"get_fund_holdings", "get_mutual_fund_details"}
    CURRENT = {"web_search", "search_company_news", "get_market_data", "research_company"}
    NAV_LOOKUP = {"search_mutual_fund_schemes", "get_mutual_fund_nav"}
    NAV_ANALYTICS = {"get_nav_history", "calculate_cagr", "calculate_volatility", "calculate_drawdown", "compare_funds"}

    def select(self, question: str, available: set[str]) -> set[str]:
        q = question.casefold()
        selected: set[str] = set()

        scenario = any(term in q for term in ("scenario", "allocate", "allocation", "more to invest", "additional invest"))
        current = any(term in q for term in ("latest", "today", "recent", "currently", "this week", "this month", "what happened", "news", "current price", "happening"))
        factsheet = any(term in q for term in ("factsheet", "annual report", "document", "disclosure"))
        company = any(term in q for term in ("compan", "indirect", "underlying"))
        portfolio = any(term in q for term in (
            "my portfolio", "in my portfolio", "my holdings", "my exposure",
            "my investments", "my investment", "my current value", "i own",
            "i invested", "i have invested", "have i invested", "i hold",
        ))
        fund = any(term in q for term in ("fund", "scheme", "holding", "invest in", "etf", "fof", "bees"))
        fund_document_fact = factsheet or any(term in q for term in (
            "objective", "benchmark", "return", "performance", "sip",
            "since inception", "expense ratio", "fund manager", "riskometer",
            "aum", "market value",
        ))

        nav_request = any(term in q for term in (
            "scheme code", "nav", "cagr", "drawdown", "volatility", "historical return", "nav history",
        ))
        lump_sum_value = (
            "since inception" in q and any(term in q for term in ("invest", "value", "worth"))
        ) or (
            any(term in q for term in ("lump sum", "lumpsum", "one-time investment"))
            and any(term in q for term in ("value", "worth", "return"))
        )

        if nav_request:
            selected |= self.NAV_LOOKUP
        if any(term in q for term in ("cagr", "drawdown", "volatility", "historical return")):
            selected |= self.NAV_LOOKUP | self.NAV_ANALYTICS
        if lump_sum_value:
            selected |= self.NAV_LOOKUP | {"calculate_lump_sum_value"}
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
        elif fund and not portfolio and not scenario and not nav_request:
            # Fund-specific document facts (including objectives, returns, and
            # SIP table values) should use the indexed evidence path by default.
            selected.add("search_financial_documents")
        if lump_sum_value and fund:
            # Factsheets can report a dated lump-sum illustration; MFapi
            # provides the NAV-derived value and its actual observation dates.
            selected.add("search_financial_documents")
        if any(term in q for term in ("historical performance", "past performance", "performance history")):
            selected |= {"get_historical_performance", "get_mutual_fund_details"}
        if current and not nav_request and not (fund_document_fact and not portfolio and not scenario):
            selected |= self.CURRENT | {"validate_analysis"}
            if portfolio:
                selected |= self.PORTFOLIO | {"get_fund_holdings", "calculate_exposure"}
        if any(term in q for term in (
            "tax impact", "tax implication", "tax liability", "tax on", "taxes on",
            "redemption", "capital gain",
        )):
            selected |= self.PORTFOLIO | {"calculate_tax_impact", "validate_analysis"}
        if any(term in q for term in ("goal", "target amount", "horizon")):
            selected |= self.PORTFOLIO | {"analyze_goal", "validate_analysis"}

        # Ambiguous questions remain flexible. Clear simple questions stay narrow.
        return (selected or available) & available
