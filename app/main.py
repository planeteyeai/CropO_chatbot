"""Main FastAPI Application Entry Point.

Orchestrates lifespan startup (Redis connect, parallel warm-up fetch, background scheduler)
and mounts static assets and API routes.
"""

from contextlib import asynccontextmanager
from pathlib import Path
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.chat import chat_router
from app.api.debug import debug_router
from app.api.plots import plots_router
from app.cache.redis_client import redis_client
from app.config.settings import settings
from app.scheduler.scheduler import start_scheduler, stop_scheduler, warmup_all_fetchers

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer() if settings.LOG_LEVEL == "JSON" else structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan managing startup warm-up and graceful shutdown."""
    logger.info("app_startup_begin", app_version="1.0.0")

    # 1. Connect to Redis hot cache
    await redis_client.connect()

    # 2. Parallel warm-up: run all registered fetchers once before serving /chat
    logger.info("executing_startup_warmup")
    await warmup_all_fetchers()

    # 3. Start background APScheduler for recurring independent fetch intervals
    start_scheduler()
    logger.info("app_startup_ready_to_serve")

    yield

    # Shutdown sequence
    logger.info("app_shutdown_begin")
    stop_scheduler()
    await redis_client.close()
    logger.info("app_shutdown_complete")


app = FastAPI(
    title="CropO Chatbot Backend",
    description="FastAPI chatbot with offline scheduled data pre-fetching in Redis and zero-external-call online retrieval",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local testing flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(chat_router)
app.include_router(debug_router)
app.include_router(plots_router)

# Mount static files at root
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
