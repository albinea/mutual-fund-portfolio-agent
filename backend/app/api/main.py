from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from ..tools import core as t

app=FastAPI(title="Mutual Fund Portfolio Intelligence Tools",version="0.1.0")
class ExposureRequest(BaseModel): user_id:str; company_id:str|None=None
class UserRequest(BaseModel): user_id:str
class SimulateRequest(BaseModel): user_id:str; additional_amount:float=Field(ge=0); allocation:dict[str,float]
class CompareRequest(BaseModel): user_id:str; additional_amount:float=Field(ge=0); scenarios:list[dict]
class SearchRequest(BaseModel): query:str; fund_id:str|None=None; company_id:str|None=None; top_k:int=Field(5,ge=1,le=50)
class ValidationRequest(BaseModel): claims:list[str]; sources:list[dict]; data_as_of_dates:list[str]|None=None

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
@app.get("/tools")
def tools():
    from ..agent.tool_registry import registry
    return {"tools":registry()}
