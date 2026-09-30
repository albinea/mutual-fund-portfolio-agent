from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Citation for a retrieved document chunk."""

    document: str = Field(min_length=1)
    page: int = Field(ge=1)
    source_url: str = Field(min_length=1)


class LLMResponse(BaseModel):
    """Validated structured response returned by the LLM."""

    answer: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[Citation] = Field(default_factory=list)