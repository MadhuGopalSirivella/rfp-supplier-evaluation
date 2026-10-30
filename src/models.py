from pydantic import BaseModel, Field


class CriterionEvaluation(BaseModel):
    criterion_id: int
    score: float | None = None
    max_score: float | None = None
    justification: str = ""
    evidence: str | None = None
    page_number: int | None = None
    evidence_status: str = "missing"


class CommercialFacts(BaseModel):
    currency: str | None = None
    one_time_cost: float | None = None
    recurring_cost: float | None = None
    total_cost: float | None = None
    assumptions: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    supplier_name: str
    criteria: list[CriterionEvaluation] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    overall_summary: str = ""
    commercial_facts: CommercialFacts = Field(default_factory=CommercialFacts)