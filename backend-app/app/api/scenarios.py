import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"


@router.get("/v1/scenarios")
async def get_scenarios():
    with open(DATA_DIR / "scenarios.json", encoding="utf-8") as f:
        data = json.load(f)
    return data
