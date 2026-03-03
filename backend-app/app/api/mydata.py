from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.mydata_service import MyDataService

router = APIRouter(prefix="/v1/mydata", tags=["mydata"])
_svc = MyDataService()


class ConsentRequest(BaseModel):
    customer_id: str
    action: str  # "grant" | "revoke"


@router.get("/customers")
async def list_customers():
    """List all demo customers for the customer selector UI."""
    return {"customers": _svc.list_customers()}


@router.post("/consent")
async def update_consent(req: ConsentRequest):
    if req.action == "grant":
        result = _svc.grant_consent(req.customer_id)
    elif req.action == "revoke":
        result = _svc.revoke_consent(req.customer_id)
    else:
        raise HTTPException(status_code=400, detail="action must be 'grant' or 'revoke'")
    if result is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return result.model_dump()


@router.get("/contracts")
async def get_contracts(customer_id: str):
    contracts = _svc.get_contracts(customer_id)
    return {"contracts": [c.model_dump() for c in contracts]}


@router.get("/customer")
async def get_customer(customer_id: str):
    customer = _svc.get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer.model_dump()
