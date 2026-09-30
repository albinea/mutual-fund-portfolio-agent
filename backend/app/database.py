"""SQLAlchemy schema for the production PostgreSQL/pgvector adapter."""
from sqlalchemy import String, Float, Date, DateTime, ForeignKey, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.sql import func
try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # Allows mock tools to run without a DB installation.
    Vector = None

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"
    id:Mapped[str]=mapped_column(String,primary_key=True)
class Fund(Base):
    __tablename__="funds"
    id:Mapped[str]=mapped_column(String,primary_key=True); name:Mapped[str]=mapped_column(String); metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
class PortfolioPosition(Base):
    __tablename__="portfolio_positions"
    id:Mapped[int]=mapped_column(primary_key=True); user_id:Mapped[str]=mapped_column(ForeignKey("users.id"),index=True); fund_id:Mapped[str]=mapped_column(ForeignKey("funds.id")); invested_amount:Mapped[float]=mapped_column(Float); current_value:Mapped[float]=mapped_column(Float); units:Mapped[float]=mapped_column(Float)
class Company(Base):
    __tablename__="companies"
    id:Mapped[str]=mapped_column(String,primary_key=True); name:Mapped[str]=mapped_column(String,index=True); sector:Mapped[str]=mapped_column(String)
class FundHolding(Base):
    __tablename__="fund_holdings"
    id:Mapped[int]=mapped_column(primary_key=True); fund_id:Mapped[str]=mapped_column(ForeignKey("funds.id"),index=True); company_id:Mapped[str]=mapped_column(ForeignKey("companies.id")); as_of_date:Mapped[Date]=mapped_column(Date,index=True); weight_percentage:Mapped[float]=mapped_column(Float); source_url:Mapped[str|None]=mapped_column(String,nullable=True)
class FinancialDocument(Base):
    __tablename__="financial_documents"
    id:Mapped[str]=mapped_column(String,primary_key=True); title:Mapped[str]=mapped_column(String); content:Mapped[str]=mapped_column(String); source_url:Mapped[str|None]=mapped_column(String,nullable=True); published_date:Mapped[Date|None]=mapped_column(Date,nullable=True); metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
    if Vector: embedding:Mapped[list[float]]=mapped_column(Vector(1536))
