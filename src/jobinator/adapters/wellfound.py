"""Wellfound (formerly AngelList Talent) job board adapter.

Wellfound has no public API. This adapter extracts job listings from the
__NEXT_DATA__ JSON blob embedded in every page, which contains Apollo Client
state with JobListingSearchResult entries.

FRAGILE NOTICE: Wellfound adapter uses __NEXT_DATA__ extraction. May break on site updates.

Two fetch modes:
  - Keyword search: GET https://wellfound.com/role/l/{keyword-slug}/remote?page=N
  - Company pages: GET https://wellfound.com/company/{slug}/jobs

Raises AdapterBrokenError immediately if the __NEXT_DATA__ script tag is missing,
so the caller can detect structural breakage and alert the user.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from jobinator.adapters.base import AdapterBrokenError
from jobinator.pipelines.normalize import RawJobDict

logger = logging.getLogger(__name__)

# Realistic User-Agent to avoid bot detection (Wellfound only — not used for API sources)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_KEYWORD_URL = "https://wellfound.com/role/l/{slug}/remote"
_COMPANY_URL = "https://wellfound.com/company/{slug}/jobs"

# Keyword slug normalization: lower, replace spaces/underscores with hyphens
_SLUG_RE = re.compile(r"[\s_]+")

# Max pages per keyword/company to avoid runaway pagination
_MAX_PAGES = 20


def _keyword_to_slug(keyword: str) -> str:
    """Normalize a keyword to a URL slug."""
    return _SLUG_RE.sub("-", keyword.strip().lower())


def extract_wellfound_next_data(html: str) -> dict:
    """Extract and parse the __NEXT_DATA__ JSON blob from a Wellfound page.

    Args:
        html: Full HTML content of a Wellfound page

    Returns:
        Parsed JSON dict from the __NEXT_DATA__ script tag

    Raises:
        AdapterBrokenError: If the __NEXT_DATA__ script tag is missing,
                            indicating a structural change on the site.
    """
    soup = BeautifulSoup(html, "lxml")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})

    if script_tag is None:
        raise AdapterBrokenError(
            "Wellfound __NEXT_DATA__ script tag not found. Adapter may be broken."
        )

    return json.loads(script_tag.string)  # type: ignore[arg-type]


def extract_job_nodes(next_data: dict) -> list[dict]:
    """Extract job listing nodes from __NEXT_DATA__ Apollo state.

    Navigates to props.pageProps.apolloState, collects all keys starting with
    "JobListingSearchResult:", and resolves the startup __ref to a company name
    from the corresponding StartupResult entry.

    Args:
        next_data: Parsed __NEXT_DATA__ dict from a Wellfound page

    Returns:
        List of job node dicts with an extra "company_name" key resolved from
        the StartupResult reference.
    """
    try:
        apollo_state = next_data["props"]["pageProps"]["apolloState"]
    except (KeyError, TypeError):
        logger.warning("Unexpected __NEXT_DATA__ structure — apolloState not found")
        return []

    jobs: list[dict] = []
    for key, node in apollo_state.items():
        if not key.startswith("JobListingSearchResult:"):
            continue

        # Dereference startup __ref to get company name
        company_name = ""
        startup_ref = node.get("startup", {})
        if isinstance(startup_ref, dict):
            ref_key = startup_ref.get("__ref", "")
            startup_node = apollo_state.get(ref_key, {})
            company_name = startup_node.get("name", "")

        job_with_company = dict(node)
        job_with_company["company_name"] = company_name
        jobs.append(job_with_company)

    return jobs


def job_node_to_raw(node: dict, company_name: str) -> RawJobDict:
    """Convert a Wellfound job node to a RawJobDict.

    Args:
        node: Job node dict from apolloState
        company_name: Resolved company name (from StartupResult)

    Returns:
        RawJobDict for downstream normalization
    """
    slug = node.get("slug") or node.get("id", "")
    return {
        "title": node.get("title", ""),
        "company": company_name,
        "description": node.get("description", ""),
        "source_url": f"https://wellfound.com/jobs/{slug}",
        "location_raw": node.get("locationNames"),
        "salary_raw": node.get("compensation"),
        "posted_at": None,  # Wellfound does not expose posted date
    }


@retry(
    wait=wait_exponential(multiplier=1, min=3, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _fetch_page(client: httpx.Client, url: str) -> str:
    """Fetch a single Wellfound page with retry on transient errors.

    Args:
        client: httpx.Client with User-Agent header set
        url: Full URL to fetch

    Returns:
        Response HTML text
    """
    response = client.get(url)
    response.raise_for_status()
    return response.text


class WellfoundAdapter:
    """Source adapter for Wellfound (formerly AngelList Talent) job board.

    Extracts job listings from the __NEXT_DATA__ JSON blob embedded in each page.
    Supports two fetch modes:
      - Keyword search via /role/l/{keyword-slug}/remote
      - Company pages via /company/{slug}/jobs

    This adapter is marked fragile=True because it relies on scraping the
    Next.js server-side rendered page structure, which may change without notice.

    FRAGILE_NOTICE: Wellfound adapter uses __NEXT_DATA__ extraction. May break on site updates.

    Attributes:
        source_id: "wellfound"
        fragile: True — SPA structure may change; health monitoring critical.
    """

    source_id = "wellfound"
    fragile = True  # SPA structure may change; health monitoring critical (D-05)
    FRAGILE_NOTICE = "Wellfound adapter uses __NEXT_DATA__ extraction. May break on site updates."

    def __init__(
        self,
        keywords: list[str],
        companies: list[str],
        delay_min: float = 3.0,
        delay_max: float = 7.0,
    ) -> None:
        """Initialize the adapter.

        Args:
            keywords: Search keywords (e.g. ["machine learning", "data science"]).
                      Each keyword is slugified for the URL.
            companies: Wellfound company slugs (e.g. ["dataco", "mlops-inc"]).
            delay_min: Minimum delay in seconds between requests.
            delay_max: Maximum delay in seconds between requests.
        """
        self.keywords = keywords
        self.companies = companies
        self.delay_min = delay_min
        self.delay_max = delay_max

    def _sleep(self) -> None:
        """Sleep a random duration between delay_min and delay_max."""
        if self.delay_min > 0 or self.delay_max > 0:
            time.sleep(random.uniform(self.delay_min, self.delay_max))

    def _fetch_jobs_from_url(self, client: httpx.Client, url: str) -> list[RawJobDict]:
        """Fetch and parse jobs from a single Wellfound page URL.

        Handles pagination for keyword search pages by checking if any new
        jobs were returned (stops when page returns no new job nodes).

        Args:
            client: httpx.Client with User-Agent header set
            url: Base Wellfound page URL

        Returns:
            List of RawJobDicts from this URL (may span multiple pages)
        """
        all_jobs: list[RawJobDict] = []

        for page in range(1, _MAX_PAGES + 1):
            paged_url = f"{url}?page={page}" if page > 1 else url

            try:
                html = _fetch_page(client, paged_url)
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Wellfound fetch failed (HTTP %d) for %s — stopping pagination",
                    exc.response.status_code,
                    paged_url,
                )
                break
            except Exception as exc:
                logger.warning("Wellfound fetch error for %s: %s — stopping", paged_url, exc)
                break

            try:
                next_data = extract_wellfound_next_data(html)
            except AdapterBrokenError:
                logger.warning(
                    "Wellfound __NEXT_DATA__ missing at %s — adapter may be broken", paged_url
                )
                raise

            nodes = extract_job_nodes(next_data)
            if not nodes:
                break  # No more job nodes on this page — stop paginating

            for node in nodes:
                company_name = node.get("company_name", "")
                all_jobs.append(job_node_to_raw(node, company_name))

            if len(nodes) < 10:  # Heuristic: partial page means we've reached the end
                break

            self._sleep()

        return all_jobs

    def fetch(self) -> list[RawJobDict]:
        """Fetch job listings from Wellfound via keyword search and company pages.

        Iterates over configured keywords (slugified to URL format) and company
        slugs. Uses random delay between requests to avoid rate limiting. Caps
        at _MAX_PAGES per session.

        Returns:
            List of RawJobDicts with keys: title, company, description,
            source_url, location_raw, salary_raw, posted_at.

        Raises:
            AdapterBrokenError: If __NEXT_DATA__ is missing (indicates site breakage).
        """
        all_jobs: list[RawJobDict] = []

        headers = {"User-Agent": USER_AGENT}

        with httpx.Client(timeout=30.0, headers=headers) as client:
            # Keyword search pages
            for i, keyword in enumerate(self.keywords):
                slug = _keyword_to_slug(keyword)
                url = _KEYWORD_URL.format(slug=slug)
                logger.debug("Fetching Wellfound keyword search: %s", url)

                try:
                    jobs = self._fetch_jobs_from_url(client, url)
                    all_jobs.extend(jobs)
                except AdapterBrokenError:
                    raise  # Propagate structural breakage immediately

                if i < len(self.keywords) - 1:
                    self._sleep()

            # Company pages
            for i, company_slug in enumerate(self.companies):
                url = _COMPANY_URL.format(slug=company_slug)
                logger.debug("Fetching Wellfound company page: %s", url)

                try:
                    jobs = self._fetch_jobs_from_url(client, url)
                    all_jobs.extend(jobs)
                except AdapterBrokenError:
                    raise  # Propagate structural breakage immediately

                if i < len(self.companies) - 1:
                    self._sleep()

        return all_jobs
