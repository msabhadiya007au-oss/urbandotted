import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from core import db, ensure_indexes, current_fy
import auth
import routes_setup
import routes_txn
import routes_inventory
import routes_analytics
import routes_ops
import routes_reports
from storage import init_storage

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Urban Dotted Expense Book API")

ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# simple in-memory rate limiter per IP
_hits: dict = {}
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "600"))


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    import time
    ip = request.client.host if request.client else "unknown"
    now = int(time.time() // 60)
    key = (ip, now)
    for k in [k for k in _hits if k[1] < now - 1]:
        _hits.pop(k, None)
    _hits[key] = _hits.get(key, 0) + 1
    if _hits[key] > RATE_LIMIT:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
    return await call_next(request)


app.include_router(auth.router)
app.include_router(routes_setup.router)
app.include_router(routes_txn.router)
app.include_router(routes_inventory.router)
app.include_router(routes_analytics.router)
app.include_router(routes_ops.router)
app.include_router(routes_reports.router)


@app.get("/api/")
async def root():
    return {"app": "Urban Dotted Expense Book", "status": "ok", "current_fy": current_fy(),
            "currency": "AUD", "timezone": "Australia/Adelaide"}


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await auth.seed_admin()
    try:
        init_storage()
        logger.info("Object storage initialised")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    pass
