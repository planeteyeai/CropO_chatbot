"""Background Scheduler Layer.

Loops over api_registry.py dynamically and registers each fetcher with an independent
APScheduler interval trigger. Contains zero API-specific logic.
"""

import asyncio
import importlib
from typing import Any, Callable, Dict, List
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config.api_registry import API_REGISTRY

logger = structlog.get_logger(__name__)

app_scheduler = AsyncIOScheduler()


def _resolve_fetcher_callable(api_config: Dict[str, Any]) -> Callable[[], Any]:
    """Dynamically load and return the async fetcher function defined in the registry entry."""
    module_path = api_config["fetcher_module"]
    func_name = api_config["fetcher_function"]
    try:
        module = importlib.import_module(module_path)
        fetcher_func = getattr(module, func_name)
        return fetcher_func
    except (ImportError, AttributeError) as exc:
        logger.error(
            "failed_to_resolve_fetcher",
            api_name=api_config.get("name"),
            module=module_path,
            function=func_name,
            error=str(exc),
        )
        raise RuntimeError(f"Could not load fetcher {module_path}.{func_name}: {exc}") from exc


async def _run_fetcher_job_wrapper(api_config: Dict[str, Any]) -> None:
    """Wrapper that catches any unhandled exceptions from a scheduled fetcher job."""
    name = api_config.get("name", "unknown")
    try:
        fetcher_func = _resolve_fetcher_callable(api_config)
        logger.info("scheduler_executing_fetcher", domain=name)
        await fetcher_func()
    except Exception as exc:
        logger.error("scheduler_job_failed", domain=name, error=str(exc))


async def warmup_all_fetchers() -> None:
    """Execute every registered fetcher concurrently in parallel on application startup.

    Guarantees the Redis cache is warm before accepting any user /chat traffic.
    """
    logger.info("starting_cache_warmup", total_apis=len(API_REGISTRY))

    tasks = []
    for api_config in API_REGISTRY:
        try:
            fetcher_func = _resolve_fetcher_callable(api_config)
            tasks.append(fetcher_func())
        except Exception as exc:
            logger.error("warmup_resolution_failed", api=api_config.get("name"), error=str(exc))

    if tasks:
        # Run all fetchers concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for api_config, result in zip(API_REGISTRY, results):
            if isinstance(result, Exception):
                logger.warning(
                    "warmup_fetcher_encountered_exception",
                    domain=api_config.get("name"),
                    error=str(result),
                )
            else:
                logger.info("warmup_fetcher_succeeded", domain=api_config.get("name"))

    logger.info("cache_warmup_completed")


def start_scheduler() -> None:
    """Register all API entries into the APScheduler and start background execution."""
    if app_scheduler.running:
        logger.info("scheduler_already_running")
        return

    logger.info("registering_jobs_to_scheduler", count=len(API_REGISTRY))

    for api_config in API_REGISTRY:
        name = api_config["name"]
        interval_sec = api_config.get("interval_seconds", 300)

        # Register interval job
        app_scheduler.add_job(
            _run_fetcher_job_wrapper,
            trigger=IntervalTrigger(seconds=interval_sec),
            args=[api_config],
            id=f"job_{name}",
            name=f"Background fetch for {name}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "scheduler_job_registered",
            domain=name,
            interval_seconds=interval_sec,
        )

    app_scheduler.start()
    logger.info("apscheduler_started")


def stop_scheduler() -> None:
    """Gracefully shutdown background scheduler."""
    if app_scheduler.running:
        app_scheduler.shutdown(wait=False)
        logger.info("apscheduler_stopped")
