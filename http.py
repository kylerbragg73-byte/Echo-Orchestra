"""
HTTP helper used by every external API call in Echo.
Wraps requests with retries, backoff, and structured logging.
"""

from __future__ import annotations

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from util.logging_setup import get_logger

log = get_logger("echo.http")


class TransientHTTPError(Exception):
    """Raised for 5xx or network errors — eligible for retry."""


class PermanentHTTPError(Exception):
    """Raised for 4xx — not eligible for retry."""


def _raise_for_status(resp: requests.Response) -> None:
    if 500 <= resp.status_code < 600:
        raise TransientHTTPError(f"{resp.status_code}: {resp.text[:300]}")
    if 400 <= resp.status_code < 500:
        # 429 is transient-ish; retry it
        if resp.status_code == 429:
            raise TransientHTTPError(f"429 rate limited: {resp.text[:300]}")
        raise PermanentHTTPError(f"{resp.status_code}: {resp.text[:300]}")


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, TransientHTTPError)),
    before_sleep=before_sleep_log(log, 20),  # INFO level
    reraise=True,
)
def post_json(url: str, *, headers: dict, json_body: dict, timeout: int = 90) -> dict:
    """POST a JSON body and return parsed JSON. Retries on 5xx / 429 / network errors."""
    log.debug("POST %s", url)
    resp = requests.post(url, headers=headers, json=json_body, timeout=timeout)
    _raise_for_status(resp)
    return resp.json()


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.RequestException, TransientHTTPError)),
    before_sleep=before_sleep_log(log, 20),
    reraise=True,
)
def get_json(url: str, *, headers: dict | None = None, params: dict | None = None, timeout: int = 60) -> dict:
    log.debug("GET %s", url)
    resp = requests.get(url, headers=headers or {}, params=params, timeout=timeout)
    _raise_for_status(resp)
    return resp.json()
