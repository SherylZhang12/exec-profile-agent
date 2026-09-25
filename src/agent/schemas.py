"""Data contracts. The LLM fills `ExtractedFields`; everything else is set by code."""
from typing import Literal
from pydantic import BaseModel, Field


class Source(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""   # short search-result excerpt
    raw: str = ""       # full page text (used by the RAG path)


class Chunk(BaseModel):
    url: str
    text: str


class Field_(BaseModel):
    """One extracted fact + its evidence. `value=None` means the system abstained."""
    value: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    note: str = ""  # only used when value is None: why it was left blank


FIELDS = ["current_role", "education", "prior_roles", "board_seats", "notable_facts"]


class ExtractedFields(BaseModel):
    """What the LLM is allowed to produce in the extract step."""
    current_role: Field_ = Field(default_factory=Field_)
    education: Field_ = Field(default_factory=Field_)
    prior_roles: Field_ = Field(default_factory=Field_)
    board_seats: Field_ = Field(default_factory=Field_)
    notable_facts: Field_ = Field(default_factory=Field_)


class ExecutiveProfile(ExtractedFields):
    # identity fields are copied from the input and never rewritten by the model
    name: str
    title: str
    company: str
    summary: str = ""
    summary_grounded: bool = False  # True only if the summary passed the grounding check
    meta: dict = Field(default_factory=dict)


class Verdict(BaseModel):
    status: Literal["ok", "retry", "abstain"]
    reasons: list[str] = Field(default_factory=list)
