from pydantic import BaseModel


class RbacScope(BaseModel):
    accessible_node_types: list[str]
    can_toggle_mock_mode: bool
    can_view_trace: bool
    can_view_regulations: bool


class Persona(BaseModel):
    id: str
    name: str
    role: str
    description: str
    rbac_scope: RbacScope
    avatar: str


class Scenario(BaseModel):
    id: str
    title: str
    description: str
    query: str
    personas: list[str]
    category: str  # "basic" | "advanced" | "mydata"
