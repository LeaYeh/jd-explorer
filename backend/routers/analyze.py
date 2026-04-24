from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.services.llm import analyze_portals

router = APIRouter()


class AnalyzeRequest(BaseModel):
    cv_url: str
    portal_urls: List[str]


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not req.portal_urls:
        raise HTTPException(status_code=400, detail="No portal URLs provided")
    try:
        results = await analyze_portals(req.cv_url, req.portal_urls)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
