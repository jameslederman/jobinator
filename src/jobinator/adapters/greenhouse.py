"""Greenhouse ATS job board adapter.

Fetches open jobs from the public Greenhouse board API:
    https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

No authentication required. Uses tenacity retry with exponential backoff.
"""

from __future__ import annotations

import logging
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from jobinator.pipelines.normalize import RawJobDict

logger = logging.getLogger(__name__)

_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"


def _strip_html(html: str) -> str:
    """Strip HTML tags from a string and return plain text."""
    return BeautifulSoup(html, "lxml").get_text(separator=" ").strip()


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _fetch_board(client: httpx.Client, board_token: str) -> list[RawJobDict]:
    """Fetch all jobs from a single Greenhouse board token.

    Retries with exponential backoff on transient HTTP errors.
    Returns an empty list on 404 (bad board token).

    Args:
        client: httpx.Client instance for making requests
        board_token: The Greenhouse board token (e.g. "anthropic")

    Returns:
        List of RawJobDict from this board, or empty list if 404.
    """
    url = _GREENHOUSE_API.format(board_token=board_token)
    response = client.get(url, params={"content": "true"})

    if response.status_code == 404:
        logger.warning("Greenhouse board token '%s' not found (404)", board_token)
        return []

    response.raise_for_status()
    data = response.json()

    jobs: list[RawJobDict] = []
    for job in data.get("jobs", []):
        raw_content = job.get("content", "")
        description = _strip_html(raw_content) if raw_content else ""

        location = job.get("location")
        location_name = location.get("name") if isinstance(location, dict) else None

        jobs.append(
            {
                "title": job.get("title", ""),
                "company": board_token,
                "description": description,
                "source_url": job.get("absolute_url", ""),
                "location_raw": location_name,
                "posted_at": job.get("updated_at"),
                "source": "greenhouse",
            }
        )

    return jobs


class GreenhouseAdapter:
    """Source adapter for the Greenhouse public board API.

    Fetches all open jobs from a list of board tokens. Board tokens are
    the company identifiers used in Greenhouse URLs (e.g. "anthropic" from
    boards.greenhouse.io/anthropic).

    Attributes:
        source_id: Adapter identifier for this source.
        fragile: False — Greenhouse has a stable public JSON API.
    """

    source_id = "greenhouse"
    fragile = False

    def __init__(self, board_tokens: list[str]) -> None:
        """Initialize the adapter with a list of board tokens.

        Args:
            board_tokens: Greenhouse board token strings, typically from
                          DiscoveryConfig.greenhouse (per D-02).
        """
        self.board_tokens = board_tokens

    def fetch(self) -> list[RawJobDict]:
        """Fetch all open jobs from all configured Greenhouse boards.

        For each board token, calls the Greenhouse jobs API with content=true
        to get full job descriptions. Retries transient errors via tenacity.
        Handles 404 gracefully (logs warning, returns empty for that board).
        Applies a brief delay between companies to avoid rate-limiting.

        Returns:
            List of RawJobDicts with keys: title, company, description,
            source_url, location_raw, posted_at, source.
        """
        all_jobs: list[RawJobDict] = []

        with httpx.Client(timeout=30.0) as client:
            for i, board_token in enumerate(self.board_tokens):
                try:
                    jobs = _fetch_board(client, board_token)
                    all_jobs.extend(jobs)
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "Greenhouse board '%s' returned HTTP %d — skipping",
                        board_token,
                        exc.response.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "Greenhouse board '%s' fetch failed: %s — skipping",
                        board_token,
                        exc,
                    )

                # Rate limit between companies (not after the last one)
                if i < len(self.board_tokens) - 1:
                    time.sleep(0.5)

        return all_jobs
