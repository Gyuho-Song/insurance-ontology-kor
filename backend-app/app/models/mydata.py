from pydantic import BaseModel


class MyDataContract(BaseModel):
    contract_id: str
    policy_id: str  # Links to Neptune Policy node ID (e.g. "Policy#hwl_h_whole_life")
    policy_name: str
    product_type: str  # "whole_life" | "health" | "life" | "savings"
    contract_status: str  # "active" | "expired" | "surrendered"
    start_date: str
    premium_amount: int  # Monthly premium in KRW
    coverage_amount: int  # Coverage amount in KRW


class MyDataConsent(BaseModel):
    customer_id: str
    customer_name: str
    consented: bool = False
    consent_timestamp: str | None = None
    contracts: list[MyDataContract] = []


class MergeContext(BaseModel):
    """In-memory merge data to inject into the subgraph post-traversal."""

    customer_node: dict  # {id, type, label, properties}
    owns_edges: list[dict]  # [{source, target, type, properties}]
    activated_policy_ids: list[str]  # Policy IDs the customer owns
