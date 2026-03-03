"""Pydantic models for v2 entity/relation extraction.

Matches GraphReadyData interface from cdk-app/lambda/shared/types.ts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    POLICY = "Policy"
    COVERAGE = "Coverage"
    EXCLUSION = "Exclusion"
    EXCEPTION = "Exception"
    DIVIDEND_METHOD = "Dividend_Method"
    REGULATION = "Regulation"
    PREMIUM_DISCOUNT = "Premium_Discount"
    SURRENDER_VALUE = "Surrender_Value"
    ELIGIBILITY = "Eligibility"
    RIDER = "Rider"
    PRODUCT_CATEGORY = "Product_Category"
    CALCULATION = "Calculation"


class RelationType(str, Enum):
    HAS_COVERAGE = "HAS_COVERAGE"
    EXCLUDED_IF = "EXCLUDED_IF"
    EXCEPTION_ALLOWED = "EXCEPTION_ALLOWED"
    GOVERNED_BY = "GOVERNED_BY"
    STRICTLY_PROHIBITED = "STRICTLY_PROHIBITED"
    EXCEPTIONALLY_ALLOWED = "EXCEPTIONALLY_ALLOWED"
    NO_DIVIDEND_STRUCTURE = "NO_DIVIDEND_STRUCTURE"
    HAS_DISCOUNT = "HAS_DISCOUNT"
    SURRENDER_PAYS = "SURRENDER_PAYS"
    REQUIRES_ELIGIBILITY = "REQUIRES_ELIGIBILITY"
    HAS_RIDER = "HAS_RIDER"
    HAS_LOAN = "HAS_LOAN"
    WAIVES_PREMIUM = "WAIVES_PREMIUM"
    OWNS = "OWNS"
    CALCULATED_BY = "CALCULATED_BY"


class EntityProvenance(BaseModel):
    source_section_id: str
    source_text: str = Field(max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)


class Entity(BaseModel):
    id: str
    type: EntityType
    label: str
    properties: dict[str, Any] = {}
    provenance: EntityProvenance


class Relation(BaseModel):
    source_id: str
    target_id: str
    type: RelationType
    properties: dict[str, Any] = {}
    provenance: EntityProvenance


class ExtractionMetadata(BaseModel):
    extracted_at: str
    model_id: str
    entity_count: int
    relation_count: int
    sections_processed: int = 0
    api_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class GraphReadyData(BaseModel):
    document_id: str
    product_name: str
    entities: list[Entity]
    relations: list[Relation]
    extraction_metadata: ExtractionMetadata


class ExtractionUnit(BaseModel):
    """A section of markdown ready for extraction."""
    section_id: str
    section_title: str
    content: str
    char_count: int = 0
    is_law: bool = False
