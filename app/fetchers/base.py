"""Base HTTP Fetcher Utilities with Retries and Resilient Fallback."""

import asyncio
from typing import Any, Dict, Optional
import httpx
import structlog

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_FACTOR = 1.5


async def async_fetch_with_retry(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
) -> Optional[Dict[str, Any]]:
    """Perform an async HTTP GET request with retries and exponential backoff.

    Returns the JSON response dict on success, or None on permanent failure.
    Catches all network and HTTP exceptions to protect the calling fetcher.
    """
    attempt = 0
    delay = 0.25

    while attempt < max_retries:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                logger.debug(
                    "http_fetch_success",
                    url=url,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                return data
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "http_fetch_attempt_failed",
                url=url,
                attempt=attempt,
                max_retries=max_retries,
                error=str(exc),
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(
                    "http_fetch_exhausted_retries",
                    url=url,
                    attempts=attempt,
                    final_error=str(exc),
                )
        except Exception as exc:
            logger.error("http_fetch_unexpected_error", url=url, error=str(exc))
            return None

    return None
