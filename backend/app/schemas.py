"""Typed contracts shared by the independently callable portfolio tools."""
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class Source(BaseModel):
    name: str
    url: str | None = None
    published_date: date | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    data_as_of: date | None = None


class ToolError(BaseModel):
    success: Literal[False] = False
    error_code: str
    message: str
    source: Source | None = None


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    success: bool = True
    source: Source | None = None
    provenance: list[Source] = Field(default_factory=list)


class FundPosition(BaseModel):
    fund_id: str
    fund_name: str
    invested_amount: float = Field(ge=0)
    current_value: float = Field(ge=0)
    units: float = Field(ge=0)
    allocation_percentage: float = Field(ge=0)


class Holding(BaseModel):
    company_id: str
    company_name: str
    sector: str
    weight_percentage: float = Field(ge=0, le=100)


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    category: str
    required_permissions: list[str] = Field(default_factory=list)
