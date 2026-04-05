"""Lever job postings API adapter.

Fetches open postings from the public Lever postings API:
    https://api.lever.co/v0/postings/{company}?mode=json&skip={offset}&limit=50

No authentication required. Paginates automatically. Uses tenacity retry.
"""

from __future__ import annotations

import logging
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobinator.pipelines.normalize import RawJobDict

logger = logging.getLogger(__name__)

_LEVER_API = "https://api.lever.co/v0/postings/{company}"
_PAGE_SIZE = 50


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _fetch_page(client: httpx.Client, company: str, skip: int) -> list[dict]:
    """Fetch a single page of Lever postings.

    Args:
        client: httpx.Client instance
        company: Lever company slug (e.g. "figma")
        skip: Number of postings to skip (pagination offset)

    Returns:
        List of raw posting dicts from Lever API.

    Raises:
        httpx.HTTPStatusError: On non-2xx response (after retries).
    """
    url = _LEVER_API.format(company=company)
    response = client.get(
        url,
        params={"mode": "json", "skip": skip, "limit": _PAGE_SIZE},
    )
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


def _map_posting(posting: dict, company: str) -> RawJobDict:
    """Map a Lever API posting dict to a RawJobDict.

    Key mappings per RESEARCH.md Pattern 3:
    - title = posting["text"]
    - company = company slug from config (per D-02)
    - description = posting.get("descriptionPlain", "")
    - source_url = posting["hostedUrl"]
    - location_raw = posting.get("categories", {}).get("location")
    - salary_raw = posting.get("salaryRange") — dict with currency, interval, min, max
    - posted_at = None — Lever public API does not expose posted date (Pitfall 5)
    """
    categories = posting.get("categories") or {}
    salary_range = posting.get("salaryRange")

    raw: RawJobDict = {
        "title": posting.get("text", ""),
        "company": company,
        "description": posting.get("descriptionPlain", ""),
        "source_url": posting.get("hostedUrl", ""),
        "location_raw": categories.get("location"),
        "posted_at": None,  # Lever public API does not expose posted date
        "source": "lever",
    }

    if salary_range is not None:
        raw["salary_raw"] = salary_range

    return raw


class LeverAdapter:
    """Source adapter for the Lever public postings API.

    Fetches all open postings from a list of company slugs, with automatic
    pagination (50 postings per page until fewer than 50 returned).

    Attributes:
        source_id: Adapter identifier for this source.
        fragile: False — Lever has a stable public JSON API.
    """

    source_id = "lever"
    fragile = False

    def __init__(self, companies: list[str]) -> None:
        """Initialize the adapter with a list of company slugs.

        Args:
            companies: Lever company slug strings, typically from
                       DiscoveryConfig.lever (per D-02).
        """
        self.companies = companies

    def fetch(self) -> list[RawJobDict]:
        """Fetch all open postings from all configured Lever companies.

        Paginates through all results (50 per page) until fewer than 50 items
        returned. Retries transient errors via tenacity. Handles HTTP errors
        gracefully (logs warning, continues to next company).

        Returns:
            List of RawJobDicts with keys: title, company, description,
            source_url, location_raw, posted_at, source, and optionally
            salary_raw (dict with currency, interval, min, max).
        """
        all_jobs: list[RawJobDict] = []

        with httpx.Client(timeout=30.0) as client:
            for i, company in enumerate(self.companies):
                try:
                    company_jobs = self._fetch_company(client, company)
                    all_jobs.extend(company_jobs)
                except httpx.HTTPStatusError as exc:
                    logger.warning(
                        "Lever company '%s' returned HTTP %d — skipping",
                        company,
                        exc.response.status_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "Lever company '%s' fetch failed: %s — skipping",
                        company,
                        exc,
                    )

                # Rate limit between companies (not after the last one)
                if i < len(self.companies) - 1:
                    time.sleep(0.5)

        return all_jobs

    def _fetch_company(self, client: httpx.Client, company: str) -> list[RawJobDict]:
        """Fetch all postings for a single Lever company with pagination.

        Args:
            client: httpx.Client instance
            company: Lever company slug

        Returns:
            List of all RawJobDicts for this company.
        """
        jobs: list[RawJobDict] = []
        skip = 0

        while True:
            page = _fetch_page(client, company, skip)

            for posting in page:
                jobs.append(_map_posting(posting, company))

            # If fewer than limit, we've reached the last page
            if len(page) < _PAGE_SIZE:
                break

            skip += _PAGE_SIZE

        return jobs
