"""LLM-neutral registry of callable tools and their schemas."""
from typing import Any
from ..tools.core import FUNCTIONS, DESCRIPTIONS
from ..schemas import ToolSpec

CATEGORY={
 "get_portfolio":"portfolio","get_fund_holdings":"portfolio","calculate_exposure":"portfolio","calculate_fund_overlap":"portfolio","calculate_sector_exposure":"portfolio","calculate_portfolio_risk":"portfolio",
 "search_financial_documents":"rag","get_mutual_fund_details":"rag","get_historical_performance":"rag",
 "web_search":"external","search_company_news":"external","get_market_data":"external","research_company":"external",
 "simulate_allocation":"analysis","compare_scenarios":"analysis","calculate_tax_impact":"analysis","analyze_goal":"analysis","validate_analysis":"analysis"}
def registry() -> list[dict[str,Any]]:
    result=[]
    for fn in FUNCTIONS:
        schema=fn.__annotations__
        result.append(ToolSpec(name=fn.__name__,description=DESCRIPTIONS[fn.__name__],input_schema={"type":"object","properties":{k:{"type":getattr(v,"__name__",str(v))} for k,v in schema.items() if k!="return"},"required":[k for k,v in schema.items() if k!="return" and "None" not in str(v) and "=" not in str(v)]},output_schema={"type":"object","properties":{"success":{"type":"boolean"},"source":{"type":["object","null"]}},"additionalProperties":True},category=CATEGORY[fn.__name__],required_permissions=["portfolio:read"] if fn.__name__ in {"get_portfolio","get_fund_holdings","calculate_exposure","calculate_fund_overlap","calculate_sector_exposure","calculate_portfolio_risk","simulate_allocation","compare_scenarios","calculate_tax_impact","analyze_goal"} else []).model_dump())
    return result
TOOLS={fn.__name__:fn for fn in FUNCTIONS}
def call_tool(name:str,arguments:dict):
    if name not in TOOLS:return {"success":False,"error_code":"UNKNOWN_TOOL","message":"Tool is not registered.","source":None}
    try:return TOOLS[name](**arguments)
    except TypeError as e:return {"success":False,"error_code":"INVALID_INPUT","message":str(e),"source":None}
