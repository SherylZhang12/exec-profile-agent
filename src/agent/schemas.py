"""Data contracts for the pipeline. The LLM must fill ExecutiveProfile exactly."""
from typing import Literal
from pydantic import BaseModel, Field


class Source(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""


class Field_(BaseModel):
    """One extracted fact + the evidence it came from. `value=None` means we abstained."""
    value: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    note: str = ""  # why blank, e.g. "no verifiable public source"


class ExecutiveProfile(BaseModel):
    name: str
    title: str
    company: str
    current_role: Field_ = Field_()
    education: Field_ = Field_()
    prior_roles: Field_ = Field_()
    board_seats: Field_ = Field_()
    notable_facts: Field_ = Field_()
    summary: str = ""  # ~150-word narrative, only from cited facts


class Verdict(BaseModel):
    """Output of the verify node: does every non-null field have a real source?"""
    status: Literal["ok", "retry", "abstain"]
    reasons: list[str] = Field(default_factory=list)
