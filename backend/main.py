import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

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

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
