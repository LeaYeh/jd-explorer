import logging
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from backend.routers import fetch, analyze, stream

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="JD Explorer")

app.include_router(fetch.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(stream.router, prefix="/api")

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
