from fastapi import HTTPException

from app.models.persona import RbacScope

RBAC_SCOPES: dict[str, RbacScope] = {
    "consultant": RbacScope(
        accessible_node_types=[
            "Policy", "Coverage", "Exclusion", "Exception",
            "Dividend_Method", "Regulation", "Premium_Discount",
            "Surrender_Value", "Eligibility", "Rider", "Product_Category",
        ],
        can_toggle_mock_mode=False,
        can_view_trace=False,
        can_view_regulations=True,
    ),
    "customer": RbacScope(
        accessible_node_types=[
            "Policy", "Coverage", "Regulation", "Premium_Discount",
            "Surrender_Value",
        ],
        can_toggle_mock_mode=False,
        can_view_trace=False,
        can_view_regulations=True,
    ),
    "underwriter": RbacScope(
        accessible_node_types=[
            "Policy", "Coverage", "Exclusion", "Exception",
            "Dividend_Method", "Regulation", "Premium_Discount",
            "Surrender_Value", "Eligibility", "Rider", "Product_Category",
        ],
        can_toggle_mock_mode=False,
        can_view_trace=True,
        can_view_regulations=True,
    ),
    "presenter": RbacScope(
        accessible_node_types=[
            "Policy", "Coverage", "Exclusion", "Exception",
            "Dividend_Method", "Regulation", "Premium_Discount",
            "Surrender_Value", "Eligibility", "Rider", "Product_Category",
        ],
        can_toggle_mock_mode=True,
        can_view_trace=True,
        can_view_regulations=True,
    ),
}


def get_rbac_scope(persona: str) -> RbacScope:
    if persona not in RBAC_SCOPES:
        raise HTTPException(status_code=400, detail=f"Unknown persona: {persona}")
    return RBAC_SCOPES[persona]


def filter_subgraph(persona: str, subgraph: dict) -> dict:
    scope = get_rbac_scope(persona)
    filtered_nodes = [
        n for n in subgraph["nodes"] if n["type"] in scope.accessible_node_types
    ]
    visible_ids = {n["id"] for n in filtered_nodes}
    filtered_edges = [
        e
        for e in subgraph["edges"]
        if e["source"] in visible_ids and e["target"] in visible_ids
    ]
    return {"nodes": filtered_nodes, "edges": filtered_edges}
