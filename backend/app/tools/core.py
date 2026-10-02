"""Mock-backed portfolio intelligence tools. Replace DataStore methods with DB/API adapters."""
from __future__ import annotations
import json, logging, math, os, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from ..schemas import Source, ToolError, ToolSpec

log = logging.getLogger("portfolio.tools")
DATA = Path(__file__).resolve().parents[2] / "mock_data"

# Django loads the repository-root .env, while the standalone agent uses
# backend/.env. Loading this file as well keeps the market adapter usable in
# both entry points without ever putting a key in source control.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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
def _run(name, fn, *, data_source="mock_data", **kwargs):
    started=time.perf_counter()
    try:
        result=fn(); ok=result.get("success",True)
        log.info("tool_call",extra={"tool_name":name,"user_id":kwargs.get("user_id"),"input_fields":sorted(k for k in kwargs if k!="user_id"),"execution_time_ms":round((time.perf_counter()-started)*1000,2),"success":ok,"data_source":data_source})
        return result
    except (ValueError, ValidationError) as e: result=_err("INVALID_INPUT",str(e))
    except Exception: log.exception("tool failure: %s",name); result=_err("TOOL_FAILURE","Tool could not complete the request.")
    return result

def _fund_positions(uid):
    p=store.portfolio(uid)
    if p is None: raise ValueError(f"Portfolio not found for user {uid}.")
    funds=store.funds(); total=sum(x["current_value"] for x in p["holdings"])
    return [{**x,"fund_name":funds.get(x["fund_id"],{}).get("name",x["fund_id"]),"allocation_percentage":round(x["current_value"]/total*100,4) if total else 0} for x in p["holdings"]], total


def _active_imported_portfolio_services(user_id: str):
    """Return Django portfolio services only when this user has an active statement.

    The tools module is also used by a standalone FastAPI demo, so Django imports
    stay lazy.  A user without an imported statement keeps the existing development
    mock behaviour; a user with one must never silently fall back to that mock data.
    """

    try:
        from django.apps import apps
        from django.conf import settings
    except ImportError:
        return None
    if not settings.configured or not apps.ready:
        return None

    from portfolio_api import services

    return services if services.active_import_for_user(user_id) is not None else None


def _source_fields(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep the legacy single-source shape while retaining every disclosure source."""

    primary = sources[0] if sources else None
    return {"source": primary, "sources": sources}


def _unavailable(message: str) -> dict[str, Any]:
    return _err("DATA_UNAVAILABLE", message)


def get_portfolio(user_id:str):
    def f():
        services = _active_imported_portfolio_services(user_id)
        if services is not None:
            return services.get_portfolio_data(user_id)
        p=store.portfolio(user_id)
        if p is None:return _err("PORTFOLIO_NOT_FOUND","Portfolio was not found.")
        positions,total=_fund_positions(user_id); invested=sum(x["invested_amount"] for x in positions)
        return {"success":True,"user_id":user_id,"total_invested":invested,"current_value":total,"funds":positions,"source":_source("Mock portfolio store",asof=date.today().isoformat())}
    return _run("get_portfolio",f,user_id=user_id)

def get_fund_holdings(fund_id:str, as_of_date:str|None=None, user_id:str|None=None):
    def f():
        services = _active_imported_portfolio_services(user_id) if user_id else None
        if services is not None:
            try:
                portfolio = services.get_portfolio_data(user_id)
                fund = next(
                    (
                        item for item in portfolio["funds"]
                        if item["fund_id"] == fund_id
                        or item["fund_name"].casefold() == fund_id.casefold()
                    ),
                    None,
                )
                if fund is None:
                    return _err("FUND_NOT_FOUND", "This fund is not in the active imported portfolio.")
                disclosure = services.imported_disclosure_exposure(user_id)
            except services.ImportedDisclosureUnavailable as exc:
                return _unavailable(str(exc))

            holdings = []
            for company in disclosure["companies"]:
                for position in company["funds"]:
                    if position["fund_name"] == fund["fund_name"]:
                        holdings.append(
                            {
                                "company_id": company["isin"] or company["company"],
                                "company_name": company["company"],
                                "sector": company["sector"],
                                "weight_percentage": position["fund_holding_percent"],
                            }
                        )
            data_as_of = max(
                (source.get("data_as_of") for source in disclosure["sources"] if source.get("data_as_of")),
                default=None,
            )
            if as_of_date and data_as_of and data_as_of > as_of_date:
                return _unavailable("No fund disclosure is available on or before the requested date.")
            return {
                "success": True,
                "fund_id": fund["fund_id"],
                "fund_name": fund["fund_name"],
                "as_of_date": data_as_of,
                "holdings": holdings,
                **_source_fields(disclosure["sources"]),
            }
        allh=store.holdings(); rec=allh.get(fund_id)
        if not rec:return _err("FUND_NOT_FOUND","Fund holdings were not found.")
        effective=date.fromisoformat(rec["as_of_date"])
        if as_of_date and effective>date.fromisoformat(as_of_date): return _err("DATA_UNAVAILABLE","No holdings are available on or before the requested date.")
        funds=store.funds(); companies=store.companies()
        return {"success":True,"fund_id":fund_id,"fund_name":funds.get(fund_id,{}).get("name",fund_id),"as_of_date":effective.isoformat(),"holdings":[{"company_id":h["company_id"],"company_name":companies.get(h["company_id"],{}).get("name",h["company_id"]),"sector":companies.get(h["company_id"],{}).get("sector","Unknown"),"weight_percentage":h["weight_percentage"]} for h in rec["holdings"]],"source":_source(rec["source"]["name"],rec["source"].get("url"),rec["source"].get("published_date"),effective.isoformat())}
    return _run("get_fund_holdings",f,fund_id=fund_id,as_of_date=as_of_date,user_id=user_id)

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
        services = _active_imported_portfolio_services(user_id)
        if services is not None:
            try:
                disclosure = services.imported_disclosure_exposure(user_id)
            except services.ImportedDisclosureUnavailable as exc:
                return _unavailable(str(exc))
            query = company_id.casefold() if company_id else None
            rows = [
                {
                    "company_id": company["isin"] or company["company"],
                    "company": company["company"],
                    "exposure_value": round(
                        company["portfolio_exposure_percent"]
                        * services.get_portfolio_data(user_id)["current_value"]
                        / 100,
                        2,
                    ),
                    "portfolio_weight_percentage": company["portfolio_exposure_percent"],
                    "fund_count": len(company["funds"]),
                    "funds": [position["fund_name"] for position in company["funds"]],
                }
                for company in disclosure["companies"]
                if query is None
                or query in {
                    company["company"].casefold(),
                    (company["isin"] or "").casefold(),
                }
            ]
            if company_id and not rows:
                return _err("COMPANY_NOT_FOUND", "Company was not found in the active fund disclosures.")
            return {"success": True, "exposures": rows, **_source_fields(disclosure["sources"])}
        positions,_=_fund_positions(user_id); total,companies,cv,_,_= _exposures(positions)
        if company_id and company_id not in companies:return _err("COMPANY_NOT_FOUND","Company was not found.")
        rows=[{"company_id":cid,"company":companies.get(cid,{}).get("name",cid),"exposure_value":round(v,2),"portfolio_weight_percentage":round(v/total*100,4) if total else 0} for cid,v in cv.items() if company_id is None or cid==company_id]
        return {"success":True,"exposures":rows,"source":_source("Mock portfolio and fund disclosures",asof=max((x.get("as_of_date","") for x in store.holdings().values()),default=None))}
    return _run("calculate_exposure",f,user_id=user_id,company_id=company_id)

def calculate_sector_exposure(user_id:str):
    def f():
        services = _active_imported_portfolio_services(user_id)
        if services is not None:
            try:
                disclosure = services.imported_disclosure_exposure(user_id)
            except services.ImportedDisclosureUnavailable as exc:
                return _unavailable(str(exc))
            return {
                "success": True,
                "sectors": [
                    {"sector": item["name"], "value": item["value"], "percentage": item["percentage"]}
                    for item in disclosure["sectors"]
                ],
                **_source_fields(disclosure["sources"]),
            }
        positions,_=_fund_positions(user_id); total,_,_,sv,_=_exposures(positions)
        return {"success":True,"sectors":[{"sector":s,"value":round(v,2),"percentage":round(v/total*100,4) if total else 0} for s,v in sorted(sv.items(),key=lambda z:-z[1])],"source":_source("Mock portfolio and fund disclosures")}
    return _run("calculate_sector_exposure",f,user_id=user_id)

def calculate_fund_overlap(user_id:str):
    def f():
        services = _active_imported_portfolio_services(user_id)
        if services is not None:
            try:
                overlap = services.calculate_imported_overlap(user_id)
            except services.ImportedDisclosureUnavailable as exc:
                return _unavailable(str(exc))
            return {
                "success": True,
                "overlapping_companies": [
                    {
                        "company_id": company["isin"] or company["company"],
                        "company_name": company["company"],
                        "fund_count": len(company["funds"]),
                        "funds": [position["fund_name"] for position in company["funds"]],
                        "effective_portfolio_exposure": company["portfolio_exposure_percent"],
                    }
                    for company in overlap["companies"]
                ],
                "sector_exposure": [
                    {"sector": item["name"], "value": item["value"], "percentage": item["percentage"]}
                    for item in overlap["sectors"]
                ],
                "overall_overlap_percent": overlap["overall_overlap_percent"],
                **_source_fields(overlap["sources"]),
            }
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

def _fund_name_for_document_search(
    fund_id: str | None,
    fund_name: str | None,
    user_id: str | None,
) -> str | None:
    """Translate portfolio identifiers to the canonical indexed scheme name."""
    if fund_name and fund_name.strip():
        return fund_name.strip()
    if not fund_id:
        return None

    if user_id:
        services = _active_imported_portfolio_services(user_id)
        if services is not None:
            portfolio = services.get_portfolio_data(user_id)
            match = next(
                (
                    item for item in portfolio.get("funds", [])
                    if str(item.get("fund_id")) == fund_id
                    or str(item.get("fund_name", "")).casefold() == fund_id.casefold()
                ),
                None,
            )
            if match:
                return str(match["fund_name"])

    mock_fund = store.funds().get(fund_id)
    if mock_fund and mock_fund.get("name"):
        return str(mock_fund["name"])
    # A model may provide the fund name in the legacy fund_id argument.
    return fund_id


def search_financial_documents(
    query: str,
    fund_id: str | None = None,
    company_id: str | None = None,
    top_k: int = 5,
    fund_name: str | None = None,
    user_id: str | None = None,
):
    """Retrieve evidence for one named fund without generating a second answer."""
    def f():
        from fundlens_rag.retrieval import retrieve_fund_documents

        scope = _fund_name_for_document_search(fund_id, fund_name, user_id)
        return retrieve_fund_documents(query, scope, top_k=top_k)

    return _run(
        "search_financial_documents", f, data_source="qdrant",
        query=query, fund_id=fund_id, company_id=company_id, top_k=top_k,
        fund_name=fund_name, user_id=user_id,
    )

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

MARKET_SYMBOLS = {
    "C001": {"symbol": "HDFCBANK", "exchange": "NSE"},
    "C002": {"symbol": "RELIANCE", "exchange": "NSE"},
    "C003": {"symbol": "INFY", "exchange": "NSE"},
    "C004": {"symbol": "ICICIBANK", "exchange": "NSE"},
    "C005": {"symbol": "LT", "exchange": "NSE"},
}


class MarketDataProviderError(Exception):
    """A safe, user-facing failure returned by a market-data provider."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MarketDataProvider:
    """Twelve Data quote adapter for configured Indian equities.

    Twelve Data's Indian exchange coverage is end-of-day.  The provider can
    return the latest available quote, but callers must retain that wording
    instead of presenting the value as a real-time tradeable price.
    """

    endpoint = "https://api.twelvedata.com/quote"
    cache_ttl_seconds = 60
    _cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def __init__(self, api_key: str | None = None):
        # MARKET_DATA_API_KEY remains a temporary backwards-compatible alias.
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or os.getenv("MARKET_DATA_API_KEY")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def get(self, company_id: str) -> dict[str, Any] | None:
        if not self.is_configured:
            raise MarketDataProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "Set TWELVE_DATA_API_KEY in backend/.env to load market quotes.",
            )

        instrument = MARKET_SYMBOLS.get(company_id)
        if instrument is None:
            return None

        cached = self._cache.get(company_id)
        if cached and time.monotonic() - cached[0] < self.cache_ttl_seconds:
            return cached[1]

        try:
            response = requests.get(
                self.endpoint,
                params={
                    "symbol": instrument["symbol"],
                    "exchange": instrument["exchange"],
                    "apikey": self.api_key,
                },
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            response_status = getattr(exc.response, "status_code", None)
            if response_status == 429:
                raise MarketDataProviderError(
                    "RATE_LIMITED",
                    "Twelve Data's request limit was reached. Wait until the next minute, then refresh the page.",
                ) from exc
            if response_status in {401, 403}:
                raise MarketDataProviderError(
                    "PROVIDER_UNAVAILABLE",
                    "Twelve Data rejected the request. Check the API key and market access on the selected plan.",
                ) from exc
            log.warning("Twelve Data returned HTTP %s for %s", response_status, company_id)
            raise MarketDataProviderError(
                "PROVIDER_UNAVAILABLE",
                "Twelve Data could not provide this quote. Please try again shortly.",
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            log.warning("Twelve Data request failed for %s: %s", company_id, type(exc).__name__)
            raise MarketDataProviderError(
                "PROVIDER_UNAVAILABLE",
                "The Twelve Data price feed could not be reached. Please try again shortly.",
            ) from exc

        if payload.get("status") == "error" or payload.get("code"):
            log.warning("Twelve Data rejected %s: %s", company_id, payload.get("code") or "error")
            raise MarketDataProviderError(
                "PROVIDER_UNAVAILABLE",
                "Twelve Data could not provide this quote. Check the API key and plan access.",
            )

        def number(field: str) -> float | None:
            value = payload.get(field)
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        price = number("close") or number("price")
        if price is None:
            raise MarketDataProviderError(
                "DATA_UNAVAILABLE",
                "Twelve Data returned no usable price for this company.",
            )
        change_percent = number("percent_change")
        previous_close = number("previous_close")
        if change_percent is None and previous_close not in (None, 0):
            change_percent = round((price - previous_close) / previous_close * 100, 4)

        quote = {
            "price": price,
            "price_change_percentage": change_percent,
            "timestamp": payload.get("datetime") or payload.get("timestamp") or payload.get("date"),
            "symbol": payload.get("symbol") or instrument["symbol"],
            "exchange": payload.get("exchange") or instrument["exchange"],
            "currency": payload.get("currency") or "INR",
            "source": "Twelve Data",
            "data_mode": "Latest available quote (Indian exchange coverage may be EOD)",
        }
        self._cache[company_id] = (time.monotonic(), quote)
        return quote


class CommunityMarketDataProvider:
    """No-key Yahoo Finance fallback based on the selected MIT-licensed project.

    The project's published public proxy may be unavailable, so this adapter uses
    its documented Yahoo cookie-and-crumb technique directly. It is still an
    unofficial community data source, and every result retains that provenance.
    """

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    timeout_seconds = 4
    _cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self._crumb: str | None = None
        self._crumb_expires_at = 0.0

    def get(self, company_id: str) -> dict[str, Any] | None:
        return self.get_many([company_id]).get(company_id)

    def get_many(self, company_ids: list[str]) -> dict[str, dict[str, Any]]:
        requested = [company_id for company_id in company_ids if company_id in MARKET_SYMBOLS]
        if not requested:
            return {}

        cached_quotes: dict[str, dict[str, Any]] = {}
        missing: list[str] = []
        for company_id in requested:
            cached = self._cache.get(company_id)
            if cached and time.monotonic() - cached[0] < MarketDataProvider.cache_ttl_seconds:
                cached_quotes[company_id] = cached[1]
            else:
                missing.append(company_id)
        if not missing:
            return cached_quotes

        symbols = ",".join(f"{MARKET_SYMBOLS[company_id]['symbol']}.NS" for company_id in missing)
        try:
            crumb = self._get_crumb()
            response = self.session.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbols, "crumb": crumb},
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("Community market fallback failed: %s", type(exc).__name__)
            raise MarketDataProviderError(
                "PROVIDER_UNAVAILABLE",
                "The community market-data fallback is unavailable. Please try again later.",
            ) from exc

        records = payload.get("quoteResponse", {}).get("result")
        if not isinstance(records, list):
            raise MarketDataProviderError(
                "PROVIDER_UNAVAILABLE",
                "The community market-data fallback returned no usable quote data.",
            )

        def number(value: Any) -> float | None:
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        by_symbol = {item.get("symbol"): item for item in records}
        for company_id in missing:
            symbol = MARKET_SYMBOLS[company_id]["symbol"]
            item = by_symbol.get(f"{symbol}.NS")
            if item is None:
                continue
            price = number(item.get("regularMarketPrice"))
            if price is None:
                continue
            market_time = item.get("regularMarketTime")
            try:
                timestamp = datetime.fromtimestamp(float(market_time), tz=timezone.utc).isoformat() if market_time else None
            except (TypeError, ValueError, OSError):
                timestamp = None
            delay = number(item.get("exchangeDataDelayedBy"))
            delay_label = f"{int(delay)}-minute delayed quote" if delay is not None else "Latest available quote"
            quote = {
                "price": price,
                "price_change_percentage": number(item.get("regularMarketChangePercent")),
                "timestamp": timestamp,
                "symbol": symbol,
                "exchange": item.get("fullExchangeName") or "NSE",
                "currency": item.get("currency") or "INR",
                "source": "Community fallback via Yahoo Finance",
                "source_url": "https://github.com/0xramm/Indian-Stock-Market-API",
                "data_mode": f"{delay_label} (Yahoo Finance community data)",
            }
            self._cache[company_id] = (time.monotonic(), quote)
            cached_quotes[company_id] = quote
        return cached_quotes

    def _get_crumb(self) -> str:
        if self._crumb and time.monotonic() < self._crumb_expires_at:
            return self._crumb
        # Yahoo may respond to this cookie bootstrap with a non-2xx page while
        # still setting the cookie needed by the following crumb request.
        self.session.get(
            "https://fc.yahoo.com",
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
        )
        response = self.session.get(
            "https://query1.finance.yahoo.com/v1/test/getcrumb",
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        crumb = response.text.strip()
        if not crumb or "<" in crumb:
            raise ValueError("Yahoo Finance did not return an authentication crumb.")
        self._crumb = crumb
        self._crumb_expires_at = time.monotonic() + 50 * 60
        return crumb


def _market_success(company_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "company_id": company_id,
        "data": data,
        "source": _source(data["source"], data.get("source_url"), asof=data.get("timestamp")),
    }


def get_market_data(
    company_id: str,
    provider: MarketDataProvider | None = None,
    fallback_provider: CommunityMarketDataProvider | None = None,
    use_fallback: bool = True,
):
    primary_error: MarketDataProviderError | None = None
    try:
        d = (provider or MarketDataProvider()).get(company_id)
    except MarketDataProviderError as exc:
        primary_error = exc
        d = None
    if d is not None:
        return _market_success(company_id, d)

    if use_fallback:
        try:
            fallback_data = (fallback_provider or CommunityMarketDataProvider()).get(company_id)
            if fallback_data is not None:
                return _market_success(company_id, fallback_data)
        except MarketDataProviderError:
            pass

    if primary_error is not None:
        return _err(primary_error.code, primary_error.message)
    return _err("DATA_UNAVAILABLE", "Market data is unavailable for this company.")
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

from .nav import (
    search_mutual_fund_schemes,
    get_mutual_fund_nav,
    calculate_lump_sum_value,
    get_nav_history,
    calculate_cagr,
    calculate_volatility,
    calculate_drawdown,
    compare_funds,
)

FUNCTIONS=[get_portfolio,get_fund_holdings,calculate_exposure,calculate_fund_overlap,calculate_sector_exposure,calculate_portfolio_risk,search_financial_documents,get_mutual_fund_details,get_historical_performance,web_search,search_company_news,get_market_data,research_company,simulate_allocation,compare_scenarios,calculate_tax_impact,analyze_goal,validate_analysis,search_mutual_fund_schemes,get_mutual_fund_nav,calculate_lump_sum_value,get_nav_history,calculate_cagr,calculate_volatility,calculate_drawdown,compare_funds]
DESCRIPTIONS={f.__name__:f.__doc__ or f.__name__.replace("_"," ").capitalize()+" using validated inputs; returns structured data and provenance." for f in FUNCTIONS}
