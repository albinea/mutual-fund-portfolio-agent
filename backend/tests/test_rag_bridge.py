from app.agent.orchestrator import AgentTurn, RequestedToolCall, SingleAgentOrchestrator
from app.agent.policy import ToolSelectionPolicy
from app.agent import tool_registry
from app.tools import core as tools
from fundlens_rag import retrieval


FUND = "HDFC ELSS - Tax Saver Fund"


def test_retrieval_returns_page_cited_chunks_for_one_resolved_fund(monkeypatch):
    monkeypatch.setattr(retrieval, "list_known_funds", lambda *_: [FUND])
    calls = []

    def fake_retrieve_documents(**kwargs):
        calls.append(kwargs)
        return [{
            "text": "The scheme returned 12%.",
            "document": "HDFC Factsheet.pdf",
            "page": 64,
            "source_url": "/documents/HDFC%20Factsheet.pdf",
            "fund_name": FUND,
            "published_date": "2026-08-31",
            "score": 0.87,
        }]

    monkeypatch.setattr(retrieval, "retrieve_documents", fake_retrieve_documents)
    result = retrieval.retrieve_fund_documents(
        "For HDFC ELSS Tax Saver Fund, what was the one-year return?",
        top_k=3,
    )

    assert result["success"]
    assert calls[0]["fund_name"] == FUND
    assert calls[0]["top_k"] == 3
    assert result["results"][0]["page"] == 64
    assert result["sources"][0]["page"] == 64
    assert result["sources"][0]["document"] == "HDFC Factsheet.pdf"


def test_retrieval_does_not_query_qdrant_without_a_single_fund(monkeypatch):
    monkeypatch.setattr(retrieval, "list_known_funds", lambda *_: [FUND])
    monkeypatch.setattr(
        retrieval,
        "retrieve_documents",
        lambda **_: (_ for _ in ()).throw(AssertionError("Qdrant must not be queried")),
    )

    result = retrieval.retrieve_fund_documents("What was its return?")

    assert not result["success"]
    assert result["error_code"] == "FUND_NOT_RESOLVED"
    assert result["results"] == []


def test_retrieval_does_not_expose_local_file_urls(monkeypatch):
    monkeypatch.setattr(retrieval, "list_known_funds", lambda *_: [FUND])
    monkeypatch.setattr(retrieval, "retrieve_documents", lambda **_: [{
        "text": "Evidence",
        "document": "HDFC Factsheet.pdf",
        "page": 64,
        "source_url": "file:///srv/app/factsheet.pdf",
        "fund_name": FUND,
    }])

    result = retrieval.retrieve_fund_documents(f"What is the return for {FUND}?")

    assert result["results"][0]["source_url"] is None
    assert result["sources"][0]["url"] is None


def test_retrieval_rejects_scope_that_conflicts_with_question(monkeypatch):
    other_fund = "HDFC Medium to Long Term Fund"
    monkeypatch.setattr(retrieval, "list_known_funds", lambda *_: [FUND, other_fund])
    monkeypatch.setattr(
        retrieval,
        "retrieve_documents",
        lambda **_: (_ for _ in ()).throw(AssertionError("Mismatched scope must not query Qdrant")),
    )

    result = retrieval.retrieve_fund_documents(
        f"What is the objective of {FUND}?", other_fund
    )

    assert not result["success"]
    assert result["error_code"] == "FUND_SCOPE_MISMATCH"


def test_search_tool_maps_portfolio_fund_id_to_canonical_name(monkeypatch):
    seen = {}
    monkeypatch.setattr(tools.store, "funds", lambda: {"F001": {"name": FUND}})

    def fake_retrieve(query, fund_scope, *, top_k):
        seen.update(query=query, fund_scope=fund_scope, top_k=top_k)
        return {"success": True, "fund_name": FUND, "results": [], "sources": [], "source": None}

    monkeypatch.setattr(retrieval, "retrieve_fund_documents", fake_retrieve)
    result = tools.search_financial_documents(
        f"What was the one-year return for {FUND}?", fund_id="F001", top_k=4
    )

    assert result["success"]
    assert seen == {
        "query": f"What was the one-year return for {FUND}?",
        "fund_scope": FUND,
        "top_k": 4,
    }


def test_fund_fact_questions_route_to_rag_but_personal_portfolio_questions_do_not():
    policy = ToolSelectionPolicy()
    available = {
        "get_portfolio",
        "get_fund_holdings",
        "search_financial_documents",
    }

    assert "search_financial_documents" in policy.select(
        f"What was the value of ₹10,000 invested since inception for {FUND}?", available
    )
    latest_return_tools = policy.select(f"What is the latest one-year return for {FUND}?", available)
    assert "search_financial_documents" in latest_return_tools
    assert "web_search" not in latest_return_tools
    assert policy.select("How much have I invested?", available) == {"get_portfolio"}


def test_orchestrator_returns_retrieved_evidence_and_page_source(monkeypatch):
    chunk = {
        "text": "The one-year return was 12%.",
        "document": "HDFC Factsheet.pdf",
        "page": 64,
        "source_url": "/documents/HDFC%20Factsheet.pdf",
        "fund_name": FUND,
        "score": 0.87,
    }

    def fake_search(query, fund_id=None, company_id=None, top_k=5, fund_name=None, user_id=None):
        return {
            "success": True,
            "results": [chunk],
            "sources": [{
                "name": "HDFC Factsheet.pdf",
                "document": "HDFC Factsheet.pdf",
                "page": 64,
                "url": "/documents/HDFC%20Factsheet.pdf",
            }],
            "source": None,
        }

    monkeypatch.setitem(tool_registry.TOOLS, "search_financial_documents", fake_search)

    class Provider:
        def start(self, **_kwargs):
            class Session:
                turns = [
                    AgentTurn(tool_calls=[RequestedToolCall(
                        "search_financial_documents", {"query": f"What was the return for {FUND}?"}
                    )]),
                    AgentTurn(text="The one-year return was 12% [HDFC Factsheet.pdf, page 64]."),
                ]

                def next_turn(self, _responses=None):
                    return self.turns.pop(0)

            return Session()

    result = SingleAgentOrchestrator(Provider()).run(
        f"What was the return for {FUND}?", "USER001"
    )

    assert result["answer_method"] == "agent_plus_rag"
    assert result["retrieved_chunks"] == [chunk]
    assert any(
        source["document"] == "HDFC Factsheet.pdf" and source["page"] == 64
        for source in result["sources"]
    )
