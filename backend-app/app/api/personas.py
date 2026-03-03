import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

DATA_DIR = Path(__file__).parent.parent / "data"


@router.get("/v1/personas")
async def get_personas():
    with open(DATA_DIR / "personas.json", encoding="utf-8") as f:
        data = json.load(f)
    return data
