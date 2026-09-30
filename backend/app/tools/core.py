"""Mock-backed portfolio intelligence tools. Replace DataStore methods with DB/API adapters."""
from __future__ import annotations
import json, logging, math, time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from ..schemas import Source, ToolError, ToolSpec

log = logging.getLogger("portfolio.tools")
DATA = Path(__file__).resolve().parents[2] / "mock_data"

class DataStore:
    def __init__(self, root: Path = DATA):
        self.root = root
    def read(self, name: str) -> dict:
        try: return json.loads((self.root / f"{name}.json").read_text())
        except (OSError, json.JSONDecodeError): return {}
    def portfolio(self, uid): return self.read("users").get(uid)
    def funds(self): return self.read("mutual_funds")
    def holdings(self): return self.read("fund_holdings")
    def companies(self): return self.read("companies")

store = DataStore()

def _err(code, message): return {"success":False,"error_code":code,"message":message,"source":None}
def _source(name, url=None, published=None, asof=None):
    return {"name":name,"url":url,"published_date":published,"retrieved_at":datetime.utcnow().isoformat()+"Z","data_as_of":asof}
def _run(name, fn, **kwargs):
    started=time.perf_counter()
    try:
        result=fn(); ok=result.get("success",True)
        log.info("tool_call",extra={"tool_name":name,"user_id":kwargs.get("user_id"),"input":{k:v for k,v in kwargs.items() if k!="user_id"},"execution_time_ms":round((time.perf_counter()-started)*1000,2),"success":ok,"data_source":"mock_data"})
        return result
    except (ValueError, ValidationError) as e: result=_err("INVALID_INPUT",str(e))
    except Exception: log.exception("tool failure: %s",name); result=_err("TOOL_FAILURE","Tool could not complete the request.")
    return result

def _fund_positions(uid):
    p=store.portfolio(uid)
    if p is None: raise ValueError(f"Portfolio not found for user {uid}.")
    funds=store.funds(); total=sum(x["current_value"] for x in p["holdings"])
    return [{**x,"fund_name":funds.get(x["fund_id"],{}).get("name",x["fund_id"]),"allocation_percentage":round(x["current_value"]/total*100,4) if total else 0} for x in p["holdings"]], total

def get_portfolio(user_id:str):
    def f():
        p=store.portfolio(user_id)
        if p is None:return _err("PORTFOLIO_NOT_FOUND","Portfolio was not found.")
        positions,total=_fund_positions(user_id); invested=sum(x["invested_amount"] for x in positions)
        return {"success":True,"user_id":user_id,"total_invested":invested,"current_value":total,"funds":positions,"source":_source("Mock portfolio store",asof=date.today().isoformat())}
    return _run("get_portfolio",f,user_id=user_id)

def get_fund_holdings(fund_id:str, as_of_date:str|None=None):
    def f():
        allh=store.holdings(); rec=allh.get(fund_id)
        if not rec:return _err("FUND_NOT_FOUND","Fund holdings were not found.")
        effective=date.fromisoformat(rec["as_of_date"])
        if as_of_date and effective>date.fromisoformat(as_of_date): return _err("DATA_UNAVAILABLE","No holdings are available on or before the requested date.")
        funds=store.funds(); companies=store.companies()
        return {"success":True,"fund_id":fund_id,"fund_name":funds.get(fund_id,{}).get("name",fund_id),"as_of_date":effective.isoformat(),"holdings":[{"company_id":h["company_id"],"company_name":companies.get(h["company_id"],{}).get("name",h["company_id"]),"sector":companies.get(h["company_id"],{}).get("sector","Unknown"),"weight_percentage":h["weight_percentage"]} for h in rec["holdings"]],"source":_source(rec["source"]["name"],rec["source"].get("url"),rec["source"].get("published_date"),effective.isoformat())}
    return _run("get_fund_holdings",f,fund_id=fund_id,as_of_date=as_of_date)

def _exposures(positions):
    companies=store.companies(); hdb=store.holdings(); total=sum(x["current_value"] for x in positions); cvals={}; svals={}; cfunds={}
    for pos in positions:
        for h in hdb.get(pos["fund_id"],{}).get("holdings",[]):
            cid=h["company_id"]; val=pos["current_value"]*h["weight_percentage"]/100; sector=companies.get(cid,{}).get("sector","Unknown")
            cvals[cid]=cvals.get(cid,0)+val; svals[sector]=svals.get(sector,0)+val
            cfunds.setdefault(cid,set()).add(pos["fund_id"])
    return total,companies,cvals,svals,cfunds

def calculate_exposure(user_id:str, company_id:str|None=None):
    def f():
        positions,_=_fund_positions(user_id); total,companies,cv,_,_= _exposures(positions)
        if company_id and company_id not in companies:return _err("COMPANY_NOT_FOUND","Company was not found.")
        rows=[{"company_id":cid,"company":companies.get(cid,{}).get("name",cid),"exposure_value":round(v,2),"portfolio_weight_percentage":round(v/total*100,4) if total else 0} for cid,v in cv.items() if company_id is None or cid==company_id]
        return {"success":True,"exposures":rows,"source":_source("Mock portfolio and fund disclosures",asof=max((x.get("as_of_date","") for x in store.holdings().values()),default=None))}
    return _run("calculate_exposure",f,user_id=user_id,company_id=company_id)

def calculate_sector_exposure(user_id:str):
    def f():
        positions,_=_fund_positions(user_id); total,_,_,sv,_=_exposures(positions)
        return {"success":True,"sectors":[{"sector":s,"value":round(v,2),"percentage":round(v/total*100,4) if total else 0} for s,v in sorted(sv.items(),key=lambda z:-z[1])],"source":_source("Mock portfolio and fund disclosures")}
    return _run("calculate_sector_exposure",f,user_id=user_id)

def calculate_fund_overlap(user_id:str):
    def f():
        positions,_=_fund_positions(user_id); total,companies,cv,sv,cf=_exposures(positions); funds=store.funds()
        overlaps=[{"company_id":cid,"company_name":companies.get(cid,{}).get("name",cid),"fund_count":len(ids),"funds":[funds.get(i,{}).get("name",i) for i in sorted(ids)],"effective_portfolio_exposure":round(cv[cid]/total*100,4) if total else 0} for cid,ids in cf.items() if len(ids)>1]
        return {"success":True,"overlapping_companies":sorted(overlaps,key=lambda x:-x["effective_portfolio_exposure"]),"sector_exposure":[{"sector":s,"value":round(v,2),"percentage":round(v/total*100,4) if total else 0} for s,v in sv.items()],"source":_source("Mock portfolio and fund disclosures")}
    return _run("calculate_fund_overlap",f,user_id=user_id)

def calculate_portfolio_risk(user_id:str, returns:dict[str,list[float]]|None=None, risk_free_rate:float=0.0):
    def f():
        positions,_=_fund_positions(user_id); total,companies,cv,sv,_=_exposures(positions)
        vol=None; sharpe=None; mdd=None
        if returns:
            names=[p["fund_id"] for p in positions]; weights={p["fund_id"]:p["current_value"]/total for p in positions} if total else {}
            n=min((len(returns.get(k,[])) for k in names),default=0)
            if n>=2:
                series=[sum(weights[k]*returns[k][i] for k in names) for i in range(n)]
                mean=sum(series)/n; vol=math.sqrt(sum((x-mean)**2 for x in series)/(n-1))*math.sqrt(252)
                sharpe=(mean*252-risk_free_rate)/vol if vol else None; wealth=peak=1.; dd=0.
                for x in series: wealth*=1+x; peak=max(peak,wealth); dd=min(dd,wealth/peak-1)
                mdd=dd
        return {"success":True,"historical_metrics":{"annualized_volatility":vol,"maximum_drawdown":mdd,"sharpe_ratio":sharpe,"periods":len(returns.get(positions[0]["fund_id"],[])) if returns and positions else 0},"concentration":{"largest_company":{"name":max(cv,key=cv.get) if cv else None,"value":round(max(cv.values()),2) if cv else 0,"percentage":round(max(cv.values())/total*100,4) if cv and total else 0},"largest_sector":{"name":max(sv,key=sv.get) if sv else None,"value":round(max(sv.values()),2) if sv else 0,"percentage":round(max(sv.values())/total*100,4) if sv and total else 0},"hhi_company":round(sum((v/total*100)**2 for v in cv.values()),2) if total else 0},"fund_overlap_count":sum(1 for _,_,_,_,cf in [_exposures(positions)] for ids in cf.values() if len(ids)>1),"inputs":{"fund_values_inr":{p["fund_id"]:p["current_value"] for p in positions},"returns_supplied":bool(returns),"risk_free_rate_annual":risk_free_rate},"methodology":"Sample standard deviation annualized with sqrt(252); drawdown from cumulative daily total returns; HHI is sum of squared company portfolio percentages. Historical metrics omitted when return series unavailable; no forward-looking claims.","source":_source("Mock portfolio and fund disclosures")}
    return _run("calculate_portfolio_risk",f,user_id=user_id)

def search_financial_documents(query:str,fund_id:str|None=None,company_id:str|None=None,top_k:int=5):
    def f(): return {"success":True,"results":[],"message":"Vector database is not configured; no documents returned.","source":_source("Unconfigured vector store")}
    return _run("search_financial_documents",f,query=query,fund_id=fund_id,company_id=company_id,top_k=top_k)

def get_mutual_fund_details(fund_id:str):
    d=store.funds().get(fund_id)
    if not d:return _err("FUND_NOT_FOUND","Fund was not found.")
    return {"success":True,"fund_id":fund_id,"details":d,"field_sources":{k:_source("Mock fund master",d.get("source_url"),asof=date.today().isoformat()) for k in d},"source":_source("Mock fund master",d.get("source_url"),asof=date.today().isoformat())}

def get_historical_performance(fund_id:str,period:str="1Y"):
    if fund_id not in store.funds():return _err("FUND_NOT_FOUND","Fund was not found.")
    return _err("DATA_UNAVAILABLE","Historical NAV series is not configured for this fund.")

def web_search(query:str,recency_days:int|None=None,max_results:int=10):
    return _err("PROVIDER_NOT_CONFIGURED","No web search provider is configured; no results returned.")
def search_company_news(company_name:str,recency_days:int=30,max_results:int=10):
    db=store.read("news"); matches=[]
    cid=next((k for k,v in store.companies().items() if v["name"].lower()==company_name.lower()),None)
    for item in db.get(cid,[]) if cid else []:
        try:
            if date.fromisoformat(item["published_date"])>=date.today()-timedelta(days=recency_days):matches.append(item)
        except (ValueError,KeyError): continue
    return {"success":True,"company":company_name,"results":matches[:max_results],"source":_source("Mock news feed")}

class MarketDataProvider:
    def get(self, company_id): return store.read("market_data").get(company_id)
def get_market_data(company_id:str,provider:MarketDataProvider|None=None):
    d=(provider or MarketDataProvider()).get(company_id)
    if d is None:return _err("DATA_UNAVAILABLE","Market data is unavailable for this company.")
    return {"success":True,"company_id":company_id,"data":d,"source":_source(d["source"],asof=d["timestamp"])}
def research_company(company_id:str):
    c=store.companies().get(company_id)
    if not c:return _err("COMPANY_NOT_FOUND","Company was not found.")
    market=get_market_data(company_id); news=search_company_news(c["name"]); docs=search_financial_documents(c["name"],company_id=company_id)
    return {"success":True,"company":c["name"],"market_data":market.get("data") if market["success"] else None,"recent_news":news["results"],"financial_documents":docs["results"],"key_factors":[],"risks":[],"sources":[x for x in [market.get("source"),news.get("source"),docs.get("source")] if x],"recommendation":None}

def _compose(user_id,allocation):
    positions,_=_fund_positions(user_id); funds=store.funds()
    for fid,amt in allocation.items():
        if fid not in funds: raise ValueError(f"Unknown fund: {fid}")
        if not isinstance(amt,(int,float)) or amt<0: raise ValueError("Allocation amounts must be non-negative numbers.")
    positions=[dict(p) for p in positions]
    by={p["fund_id"]:p for p in positions}
    for fid,amt in allocation.items():
        if fid in by: by[fid]["current_value"]+=amt; by[fid]["invested_amount"]+=amt
        else: positions.append({"fund_id":fid,"fund_name":funds[fid]["name"],"current_value":amt,"invested_amount":amt,"units":0})
    total=sum(p["current_value"] for p in positions)
    for p in positions:p["allocation_percentage"]=p["current_value"]/total*100 if total else 0
    return positions
def _snapshot(positions):
    total,companies,cv,sv,cf=_exposures(positions)
    return {"total_value":round(total,2),"fund_allocation":[{"fund_id":p["fund_id"],"fund_name":p["fund_name"],"value":round(p["current_value"],2),"percentage":round(p["allocation_percentage"],4)} for p in positions],"company_exposure":[{"company":companies.get(k,{}).get("name",k),"value":round(v,2),"percentage":round(v/total*100,4) if total else 0,"fund_count":len(cf[k])} for k,v in cv.items()],"sector_exposure":[{"sector":k,"value":round(v,2),"percentage":round(v/total*100,4) if total else 0} for k,v in sv.items()],"largest_company_percentage":round(max(cv.values())/total*100,4) if cv and total else 0,"overlapping_company_count":sum(len(x)>1 for x in cf.values())}
def simulate_allocation(user_id:str,additional_amount:float,allocation:dict[str,float]):
    def f():
        if additional_amount<0 or abs(sum(allocation.values())-additional_amount)>0.01:raise ValueError("Allocation must be non-negative and sum to additional_amount.")
        before=_snapshot(_fund_positions(user_id)[0]); after=_snapshot(_compose(user_id,allocation))
        return {"success":True,"additional_amount":additional_amount,"before":before,"after":after,"assumptions":["Contributions are added at current value; units and transaction costs are not modeled.","Underlying fund holdings remain unchanged at latest disclosed weights."],"source":_source("Mock portfolio and fund disclosures")}
    return _run("simulate_allocation",f,user_id=user_id,additional_amount=additional_amount,allocation=allocation)
def compare_scenarios(user_id:str,additional_amount:float,scenarios:list[dict]):
    results=[]
    for scenario in scenarios:
        r=simulate_allocation(user_id,additional_amount,scenario.get("allocation",{}))
        if not r["success"]:return r
        results.append({"name":scenario.get("name","Scenario"),**r["after"]})
    return {"success":True,"scenarios":results,"selection":"No scenario is selected or ranked as best.","source":_source("Mock portfolio and fund disclosures")}

def calculate_tax_impact(user_id:str,redemptions:dict[str,float],as_of_date:str|None=None):
    return _err("DATA_UNAVAILABLE","Tax calculation requires purchase lots, holding periods, investor tax status, and current tax rules.")
def analyze_goal(user_id:str,target_amount:float,horizon_months:int,monthly_contribution:float=0):
    if target_amount<=0 or horizon_months<=0 or monthly_contribution<0:return _err("INVALID_INPUT","Target and horizon must be positive; contribution cannot be negative.")
    return {"success":True,"target_amount":target_amount,"horizon_months":horizon_months,"monthly_contribution":monthly_contribution,"contributions_total":monthly_contribution*horizon_months,"investment_return_assumption":None,"projected_value":None,"message":"No return projection is provided without an explicitly supplied assumption and suitability context.","source":None}
def validate_analysis(claims:list[str],sources:list[dict],data_as_of_dates:list[str]|None=None):
    problems=[]
    for i,c in enumerate(claims):
        if any(term in c.lower() for term in ("guaranteed return","will maximize profit","certain to outperform","risk-free return")):problems.append({"claim_index":i,"issue":"UNSUPPORTED_CERTAINTY"})
        if i>=len(sources) or not sources[i].get("source_url") and not sources[i].get("url") and not sources[i].get("source_name") and not sources[i].get("name"):problems.append({"claim_index":i,"issue":"MISSING_SOURCE"})
    return {"success":True,"valid":not problems,"issues":problems,"checks":["No guaranteed-return language","Each claim has source metadata"],"source":None}

from .nav import get_nav_history, calculate_cagr, calculate_volatility, calculate_drawdown, compare_funds

FUNCTIONS=[get_portfolio,get_fund_holdings,calculate_exposure,calculate_fund_overlap,calculate_sector_exposure,calculate_portfolio_risk,search_financial_documents,get_mutual_fund_details,get_historical_performance,web_search,search_company_news,get_market_data,research_company,simulate_allocation,compare_scenarios,calculate_tax_impact,analyze_goal,validate_analysis,get_nav_history,calculate_cagr,calculate_volatility,calculate_drawdown,compare_funds]
DESCRIPTIONS={f.__name__:f.__doc__ or f.__name__.replace("_"," ").capitalize()+" using validated inputs; returns structured data and provenance." for f in FUNCTIONS}
