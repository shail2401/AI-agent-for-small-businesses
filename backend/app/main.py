from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, engine
from .routers import analytics, copilot, payments
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if settings.auto_seed:
        seed()
    yield


app = FastAPI(title="Luke's Diner Copilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
for r in (analytics.router, copilot.router, payments.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}
