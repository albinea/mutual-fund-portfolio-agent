from app.tools import core as t

def test_portfolio_totals():
    p=t.get_portfolio("USER001")
    assert p["success"] and p["total_invested"]==110000 and p["current_value"]==125000

def test_effective_exposure():
    r=t.calculate_exposure("USER001","C001")["exposures"][0]
    assert r["exposure_value"]==10300
    assert round(r["portfolio_weight_percentage"],2)==8.24

def test_overlap_and_sector_exposure():
    overlap=t.calculate_fund_overlap("USER001")["overlapping_companies"]
    bank=next(x for x in overlap if x["company_id"]=="C001")
    assert bank["fund_count"]==3 and bank["effective_portfolio_exposure"]==8.24
    sectors=t.calculate_sector_exposure("USER001")["sectors"]
    financial=next(x for x in sectors if x["sector"]=="Financial Services")
    assert financial["value"]==14530

def test_simulation_conserves_value():
    result=t.simulate_allocation("USER001",30000,{"F001":5000,"F002":10000,"F003":15000})
    assert result["success"] and result["after"]["total_value"]==155000
    assert round(sum(x["percentage"] for x in result["after"]["fund_allocation"]),6)==100

def test_errors_and_validation():
    assert t.get_portfolio("absent")["error_code"]=="PORTFOLIO_NOT_FOUND"
    v=t.validate_analysis(["Guaranteed return of 20%"],[{}])
    assert not v["valid"] and len(v["issues"])==2
