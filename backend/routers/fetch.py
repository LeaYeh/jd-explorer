from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.scraper import fetch_page_text

router = APIRouter()


class FetchRequest(BaseModel):
    url: str


@router.post("/fetch")
async def fetch_page(req: FetchRequest):
    try:
        text = await fetch_page_text(req.url)
        return {"text": text, "url": req.url}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
