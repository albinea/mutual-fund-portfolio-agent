from app.agent.orchestrator import AgentTurn, RequestedToolCall, SingleAgentOrchestrator
from app.agent.tool_registry import call_tool, registry
from app.agent import tool_registry
from app.tools import core as tools


class ScriptedSession:
    def __init__(self, turns):
        self.turns = list(turns)
        self.responses = []

    def next_turn(self, tool_responses=None):
        self.responses.append(tool_responses)
        return self.turns.pop(0)


class ScriptedProvider:
    def __init__(self, turns):
        self.session = ScriptedSession(turns)
        self.tool_names = set()

    def start(self, **kwargs):
        self.tool_names = {tool["name"] for tool in kwargs["tools"]}
        return self.session


def call(name, **arguments):
    return AgentTurn(tool_calls=[RequestedToolCall(name, arguments)])


def test_simple_portfolio_question_has_narrow_routing_and_no_web():
    provider = ScriptedProvider([call("get_portfolio"), AgentTurn(text="You invested ₹110,000.")])
    result = SingleAgentOrchestrator(provider).run("How much have I invested?", "USER001")
    assert result["success"]
    assert provider.tool_names == {"get_portfolio"}
    assert [item["tool"] for item in result["tool_trace"]] == ["get_portfolio"]
    assert result["sources"]


def test_current_portfolio_question_enables_research_tools():
    provider = ScriptedProvider([call("web_search", query="portfolio company news"), AgentTurn(text="Current search is unavailable.")])
    result = SingleAgentOrchestrator(provider).run("Latest news about companies in my portfolio", "USER001")
    assert {"web_search", "search_company_news", "get_market_data"} <= provider.tool_names
    assert result["tool_trace"][0]["error_code"] == "PROVIDER_NOT_CONFIGURED"
    assert result["metadata"]["data_errors"]


def test_historical_performance_routes_to_internal_fund_data():
    provider = ScriptedProvider([call("get_historical_performance", fund_id="F001"), AgentTurn(text="History is unavailable.")])
    result = SingleAgentOrchestrator(provider).run("Show the historical performance of Fund A", "USER001")
    assert "get_historical_performance" in provider.tool_names
    assert "web_search" not in provider.tool_names
    assert result["tool_trace"][0]["error_code"] == "DATA_UNAVAILABLE"


def test_chat_can_fetch_fund_nav_by_name_from_mfapi(monkeypatch):
    from app.tools import nav

    nav._search_cache.clear()
    nav._latest_cache.clear()
    scheme_name = "HDFC ELSS Tax Saver Fund - Regular Plan - Growth"

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        if url.endswith("/search"):
            return Response([{"schemeCode": 9090, "schemeName": scheme_name}])
        assert url.endswith("/9090/latest")
        return Response({
            "meta": {"scheme_code": 9090, "scheme_name": scheme_name},
            "data": [{"date": "01-10-2026", "nav": "250.125"}],
        })

    monkeypatch.setattr(nav.requests, "get", fake_get)
    provider = ScriptedProvider([
        call("get_mutual_fund_nav", fund_name=scheme_name),
        AgentTurn(text="The latest NAV was ₹250.125 on 1 October 2026 [MFapi.in]."),
    ])
    result = SingleAgentOrchestrator(provider).run(
        "What is the latest NAV for HDFC ELSS Tax Saver Fund - Regular Plan - Growth?",
        "USER001",
    )

    nav_result = provider.session.responses[1][0].result
    assert "get_mutual_fund_nav" in provider.tool_names
    assert nav_result["success"] and nav_result["scheme_code"] == 9090
    assert nav_result["nav"] == 250.125
    assert result["answer_method"] == "agent_plus_mfapi"
    assert any("MFapi.in" in source["name"] for source in result["sources"])


def test_fund_nav_and_sip_questions_route_to_the_right_sources():
    from app.agent.policy import ToolSelectionPolicy

    available = {item["name"] for item in registry(for_model=True)}
    policy = ToolSelectionPolicy()
    nav_tools = policy.select("What is the latest NAV for HDFC ELSS Tax Saver Fund?", available)
    assert nav_tools == {"search_mutual_fund_schemes", "get_mutual_fund_nav"}

    sip_tools = policy.select(
        "What was the market value for the 1-year SIP of HDFC ELSS Tax Saver Fund?",
        available,
    )
    assert "search_financial_documents" in sip_tools
    assert "calculate_lump_sum_value" not in sip_tools
    assert "get_mutual_fund_nav" not in sip_tools

    inception_tools = policy.select(
        "What was the value of ₹10,000 invested since inception for HDFC ELSS Tax Saver Fund?",
        available,
    )
    assert {"search_financial_documents", "calculate_lump_sum_value"} <= inception_tools


def test_sequential_portfolio_holdings_exposure_chain():
    provider = ScriptedProvider([
        call("get_portfolio"),
        AgentTurn(tool_calls=[
            RequestedToolCall("get_fund_holdings", {"fund_id": "F001"}),
            RequestedToolCall("get_fund_holdings", {"fund_id": "F002"}),
            RequestedToolCall("get_fund_holdings", {"fund_id": "F003"}),
        ]),
        call("calculate_exposure"),
        AgentTurn(text="The calculated company exposures are available."),
    ])
    result = SingleAgentOrchestrator(provider).run("Which companies am I indirectly invested in?", "USER001")
    assert [item["tool"] for item in result["tool_trace"]] == [
        "get_portfolio", "get_fund_holdings", "get_fund_holdings", "get_fund_holdings", "calculate_exposure"
    ]
    exposure_response = provider.session.responses[-1][0].result
    assert exposure_response["success"] and exposure_response["exposures"][0]["exposure_value"] > 0


def test_scenario_uses_actual_portfolio_and_validation():
    scenarios = [
        {"name": "Even", "allocation": {"F001": 10000, "F002": 10000, "F003": 10000}},
        {"name": "Flexi and mid", "allocation": {"F002": 15000, "F003": 15000}},
    ]
    provider = ScriptedProvider([
        call("get_portfolio"),
        call("compare_scenarios", additional_amount=30000, scenarios=scenarios),
        call("validate_analysis", claims=[], sources=[]),
        AgentTurn(text="Two calculated scenarios were compared."),
    ])
    result = SingleAgentOrchestrator(provider).run(
        "I have ₹30,000 more to invest. Show me different allocation scenarios based on my current portfolio.",
        "USER001",
    )
    comparison = provider.session.responses[2][0].result
    assert comparison["success"]
    assert all(item["total_value"] == 155000 for item in comparison["scenarios"])
    assert [item["tool"] for item in result["tool_trace"]][-1] == "validate_analysis"


def test_invalid_arguments_and_unknown_fund_fail_without_fabrication():
    provider = ScriptedProvider([
        call("get_fund_holdings"),
        call("get_fund_holdings", fund_id="UNKNOWN"),
        AgentTurn(text="Holdings could not be retrieved."),
    ])
    result = SingleAgentOrchestrator(provider).run("What does Fund A invest in?", "USER001")
    assert [item["error_code"] for item in result["tool_trace"]] == ["INVALID_INPUT", "FUND_NOT_FOUND"]
    assert len(result["metadata"]["data_errors"]) == 2


def test_model_cannot_override_authenticated_user_id():
    provider = ScriptedProvider([
        call("get_portfolio", user_id="ATTACKER"),
        AgentTurn(text="Retrieved the authenticated portfolio."),
    ])
    result = SingleAgentOrchestrator(provider).run("Show my portfolio", "USER001")
    tool_result = provider.session.responses[1][0].result
    assert tool_result["success"] and tool_result["user_id"] == "USER001"
    assert result["success"]


def test_registry_has_real_json_schemas_and_hides_user_id_from_model():
    public = {item["name"]: item for item in registry()}
    model = {item["name"]: item for item in registry(for_model=True)}
    assert "user_id" in public["get_portfolio"]["input_schema"]["properties"]
    assert "user_id" not in model["get_portfolio"]["input_schema"]["properties"]
    assert model["simulate_allocation"]["input_schema"]["properties"]["additional_amount"]["type"] == "number"


def test_direct_registry_calls_remain_backwards_compatible():
    result = call_tool("get_portfolio", {"user_id": "USER001"})
    assert result["success"] and result["total_invested"] == 110000


def test_database_adapter_failure_is_structured(monkeypatch):
    def fail(_user_id):
        raise OSError("database unavailable")

    monkeypatch.setattr(tools.store, "portfolio", fail)
    provider = ScriptedProvider([call("get_portfolio"), AgentTurn(text="Portfolio data is unavailable.")])
    result = SingleAgentOrchestrator(provider).run("Show my portfolio", "USER001")
    assert result["tool_trace"][0]["error_code"] == "TOOL_FAILURE"
    assert result["metadata"]["data_errors"][0]["error_code"] == "TOOL_FAILURE"


def test_empty_portfolio_is_not_treated_as_missing(monkeypatch):
    monkeypatch.setattr(tools.store, "portfolio", lambda _user_id: {"holdings": []})
    provider = ScriptedProvider([call("get_portfolio"), AgentTurn(text="Your portfolio is empty.")])
    result = SingleAgentOrchestrator(provider).run("What mutual funds do I own?", "USER001")
    tool_result = provider.session.responses[1][0].result
    assert tool_result["success"] and tool_result["total_invested"] == 0 and tool_result["funds"] == []
    assert result["success"]


def test_failed_validation_blocks_final_claims():
    provider = ScriptedProvider([
        call("validate_analysis", claims=["Guaranteed return of 20%"], sources=[{}]),
        AgentTurn(text="This scenario guarantees 20%."),
    ])
    result = SingleAgentOrchestrator(provider).run("Show an allocation scenario for more to invest", "USER001")
    assert not result["success"]
    assert result["error_code"] == "ANALYSIS_VALIDATION_FAILED"


def test_current_request_forces_validation_when_model_skips_tools():
    provider = ScriptedProvider([AgentTurn(
        text="I cannot provide a single company recommendation without suitability information."
    )])
    result = SingleAgentOrchestrator(provider).run(
        "I have 30k, which company should I invest this month? Give one answer.",
        "USER001",
    )
    assert result["success"]
    assert [item["tool"] for item in result["tool_trace"]] == ["validate_analysis"]
    assert result["tool_trace"][0]["success"]


def test_unsupported_company_recommendation_is_blocked_without_sources():
    provider = ScriptedProvider([AgentTurn(text="Invest in HDFC Bank this month.")])
    result = SingleAgentOrchestrator(provider).run(
        "I have 30k, which company should I invest this month? Give one answer.",
        "USER001",
    )
    assert not result["success"]
    assert result["error_code"] == "ANALYSIS_VALIDATION_FAILED"
    assert result["tool_trace"][0]["error_code"] == "VALIDATION_FAILED"


def test_rag_failure_is_returned_to_agent(monkeypatch):
    def failed_rag(query: str, fund_id: str | None = None, company_id: str | None = None, top_k: int = 5):
        return {"success": False, "error_code": "VECTOR_STORE_UNAVAILABLE", "message": "RAG is unavailable.", "source": None}

    monkeypatch.setitem(tool_registry.TOOLS, "search_financial_documents", failed_rag)
    provider = ScriptedProvider([
        call("search_financial_documents", query="latest Fund A factsheet"),
        AgentTurn(text="The trusted document store is unavailable."),
    ])
    result = SingleAgentOrchestrator(provider).run("What does the latest Fund A factsheet say?", "USER001")
    assert result["tool_trace"][0]["error_code"] == "VECTOR_STORE_UNAVAILABLE"
    assert result["metadata"]["data_errors"]


def test_ollama_adapter_sends_and_receives_native_tool_calls():
    from app.agent.ollama import OllamaSession
    from app.agent.orchestrator import ToolResponse

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.requests = []
            self.responses = [
                Response({"message": {"role": "assistant", "content": "", "tool_calls": [{
                    "type": "function", "function": {"name": "get_portfolio", "arguments": {}}
                }]}, "prompt_eval_count": 20, "eval_count": 5}),
                Response({"message": {"role": "assistant", "content": "You invested ₹110,000."}, "prompt_eval_count": 30, "eval_count": 10}),
            ]

        def post(self, path, json):
            self.requests.append((path, json))
            return self.responses.pop(0)

    client = Client()
    session = OllamaSession(
        client=client, model="gemma4:31b", system_prompt="system", question="How much?",
        context=[], tools=registry(for_model=True, names={"get_portfolio"}),
    )
    first = session.next_turn()
    assert first.tool_calls[0].name == "get_portfolio"
    assert client.requests[0][0] == "/api/chat"
    assert client.requests[0][1]["tools"][0]["function"]["name"] == "get_portfolio"
    final = session.next_turn([ToolResponse("call-1", "get_portfolio", {"success": True, "total_invested": 110000})])
    assert final.text == "You invested ₹110,000."
    assert client.requests[1][1]["messages"][-1]["role"] == "tool"
    assert client.requests[1][1]["messages"][-1]["tool_name"] == "get_portfolio"
    usage = session.usage_snapshot()[0]
    assert usage["role"] == "answer"
    assert usage["requests"] == 2
    assert usage["input_tokens"] == 50
    assert usage["output_tokens"] == 15


def test_chat_api_maps_message_to_agent(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import main

    captured = {}

    def answer(**kwargs):
        captured.update(kwargs)
        return {"success": True, "answer": "ok", "sources": [], "tool_trace": [], "metadata": {}}

    monkeypatch.setattr(main, "answer_question", answer)
    response = TestClient(main.app).post("/api/chat", json={
        "user_id": "USER001",
        "message": "Do my funds overlap?",
        "conversation_context": [{"role": "assistant", "content": "Previous answer"}],
    })
    assert response.status_code == 200 and response.json()["answer"] == "ok"
    assert captured["question"] == "Do my funds overlap?"
    assert captured["conversation_context"][0]["role"] == "assistant"
