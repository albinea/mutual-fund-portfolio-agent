from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Literal
from ..tools import core as t
from ..agent.ollama import answer_question

app=FastAPI(title="Mutual Fund Portfolio Intelligence Agent",version="0.2.0")
class ExposureRequest(BaseModel): user_id:str; company_id:str|None=None
class UserRequest(BaseModel): user_id:str
class SimulateRequest(BaseModel): user_id:str; additional_amount:float=Field(ge=0); allocation:dict[str,float]
class CompareRequest(BaseModel): user_id:str; additional_amount:float=Field(ge=0); scenarios:list[dict]
class SearchRequest(BaseModel): query:str; fund_id:str|None=None; company_id:str|None=None; top_k:int=Field(5,ge=1,le=50)
class ValidationRequest(BaseModel): claims:list[str]; sources:list[dict]; data_as_of_dates:list[str]|None=None
class NavMetricRequest(BaseModel): scheme_code:int=Field(gt=0); years:int=Field(gt=0)
class FundComparisonRequest(BaseModel): scheme_codes:list[int]=Field(min_length=2); years:int=Field(gt=0)
class AgentRequest(BaseModel): user_id:str=Field(min_length=1); question:str=Field(min_length=1, max_length=4000)
class ConversationMessage(BaseModel): role:Literal["user","assistant","model"]; content:str=Field(min_length=1,max_length=4000)
class ChatRequest(BaseModel):
    user_id:str=Field(min_length=1)
    message:str=Field(min_length=1,max_length=4000)
    conversation_context:list[ConversationMessage]=Field(default_factory=list,max_length=20)

@app.get("/portfolio/{user_id}")
def portfolio(user_id:str): return t.get_portfolio(user_id)
@app.get("/fund/{fund_id}")
def fund(fund_id:str): return t.get_mutual_fund_details(fund_id)
@app.get("/fund/{fund_id}/holdings")
def holdings(fund_id:str,as_of_date:str|None=None): return t.get_fund_holdings(fund_id,as_of_date)
@app.post("/portfolio/exposure")
def exposure(req:ExposureRequest): return t.calculate_exposure(req.user_id,req.company_id)
@app.post("/portfolio/overlap")
def overlap(req:UserRequest): return t.calculate_fund_overlap(req.user_id)
@app.post("/portfolio/sector-exposure")
def sectors(req:UserRequest): return t.calculate_sector_exposure(req.user_id)
@app.post("/portfolio/risk")
def risk(req:UserRequest): return t.calculate_portfolio_risk(req.user_id)
@app.post("/rag/search")
def rag(req:SearchRequest): return t.search_financial_documents(**req.model_dump())
@app.get("/market/{company_id}")
def market(company_id:str): return t.get_market_data(company_id)
@app.get("/news/{company_id}")
def news(company_id:str):
    c=t.store.companies().get(company_id)
    if not c:return {"success":False,"error_code":"COMPANY_NOT_FOUND","message":"Company was not found.","source":None}
    return t.search_company_news(c["name"])
@app.post("/analysis/simulate")
def simulate(req:SimulateRequest): return t.simulate_allocation(**req.model_dump())
@app.post("/analysis/compare")
def compare(req:CompareRequest): return t.compare_scenarios(**req.model_dump())
@app.post("/analysis/validate")
def validate(req:ValidationRequest): return t.validate_analysis(**req.model_dump())
@app.get("/nav/{scheme_code}")
def nav_history(scheme_code:int,limit:int=30): return t.get_nav_history(scheme_code,limit)
@app.post("/nav/cagr")
def nav_cagr(req:NavMetricRequest): return t.calculate_cagr(**req.model_dump())
@app.post("/nav/volatility")
def nav_volatility(req:NavMetricRequest): return t.calculate_volatility(**req.model_dump())
@app.post("/nav/drawdown")
def nav_drawdown(req:NavMetricRequest): return t.calculate_drawdown(**req.model_dump())
@app.post("/nav/compare")
def nav_compare(req:FundComparisonRequest): return t.compare_funds(**req.model_dump())
@app.post("/agent/query")
def agent_query(req:AgentRequest): return answer_question(**req.model_dump())
@app.post("/api/chat")
def chat(req:ChatRequest):
    return answer_question(
        question=req.message,
        user_id=req.user_id,
        conversation_context=[item.model_dump() for item in req.conversation_context],
    )
@app.get("/tools")
def tools():
    from ..agent.tool_registry import registry
    return {"tools":registry()}
