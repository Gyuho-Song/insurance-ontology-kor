from enum import Enum

from pydantic import BaseModel


class IntentType(str, Enum):
    COVERAGE_INQUIRY = "coverage_inquiry"
    DIVIDEND_CHECK = "dividend_check"
    EXCLUSION_EXCEPTION = "exclusion_exception"
    SURRENDER_VALUE = "surrender_value"
    DISCOUNT_ELIGIBILITY = "discount_eligibility"
    REGULATION_INQUIRY = "regulation_inquiry"
    LOAN_INQUIRY = "loan_inquiry"
    PREMIUM_WAIVER = "premium_waiver"
    POLICY_COMPARISON = "policy_comparison"
    CALCULATION_INQUIRY = "calculation_inquiry"
    ELIGIBILITY_INQUIRY = "eligibility_inquiry"
    RIDER_INQUIRY = "rider_inquiry"
    GENERAL_INQUIRY = "general_inquiry"


class Entity(BaseModel):
    name: str
    type: str
    value: str


class Intent(BaseModel):
    type: IntentType
    confidence: float
    entities: list[Entity]
    requires_regulation: bool
    complexity: str  # "simple" | "complex"
