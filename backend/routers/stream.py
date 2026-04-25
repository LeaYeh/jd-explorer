import json
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List

from backend.services.llm import analyze_portals_stream

log = logging.getLogger(__name__)
router = APIRouter()


class StreamRequest(BaseModel):
    cv_url: str
    portal_urls: List[str]


@router.post("/analyze/stream")
async def stream_analyze(req: StreamRequest):
    async def generate():
        try:
            async for event in analyze_portals_stream(req.cv_url, req.portal_urls):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            log.exception("[stream] unhandled error")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # tell Traefik not to buffer
        },
    )
