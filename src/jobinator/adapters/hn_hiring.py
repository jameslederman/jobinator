"""HN Who's Hiring adapter.

Discovers the latest "Ask HN: Who is Hiring?" threads via the Algolia HN Search API
and parses top-level comments into RawJobDicts. Comments use a conventional
pipe-delimited format: Company | Title | Location | Salary | ...

API endpoints:
    Search: https://hn.algolia.com/api/v1/search_by_date
    Item:   https://hn.algolia.com/api/v1/items/{story_id}

No authentication required. Algolia provides this officially for HN.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from jobinator.pipelines.normalize import RawJobDict

logger = logging.getLogger(__name__)

_ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ALGOLIA_ITEM = "https://hn.algolia.com/api/v1/items/{story_id}"

# Salary pattern: $200k-$300k, $150,000 - $200,000, etc.
_SALARY_RE = re.compile(
    r"\$[\d,]+[kK]?\s*[-\u2013]\s*\$?[\d,]+[kK]?|\$[\d,]+[kK]",
    re.IGNORECASE,
)

# URL pattern
_URL_RE = re.compile(r"https?://\S+")


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _get(client: httpx.Client, url: str, **params: object) -> dict:
    """GET a JSON endpoint with retry on transient errors."""
    response = client.get(url, params=params)  # type: ignore[arg-type]
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


def find_latest_hn_hiring_threads(months_back: int = 1) -> list[int]:
    """Find the latest N HN Who's Hiring thread IDs via Algolia.

    Searches for threads posted by the "whoishiring" HN account.

    Args:
        months_back: How many months of threads to return (default 1 = latest only)

    Returns:
        List of HN story IDs (ints), most-recent first.

    Raises:
        RuntimeError: If no threads are found.
    """
    with httpx.Client(timeout=30.0) as client:
        data = _get(
            client,
            _ALGOLIA_SEARCH,
            tags="story,author_whoishiring",
            hitsPerPage=months_back,
        )

    hits = data.get("hits", [])
    if not hits:
        raise RuntimeError("No Who is Hiring thread found via Algolia")

    return [int(hit["objectID"]) for hit in hits]


def fetch_thread_comments(story_id: int) -> list[dict]:
    """Fetch top-level comments for an HN story.

    Only returns top-level children — does NOT recurse into nested replies.

    Args:
        story_id: HN story ID (integer)

    Returns:
        List of top-level comment dicts (each has id, text, author, created_at, children)
    """
    url = _ALGOLIA_ITEM.format(story_id=story_id)
    with httpx.Client(timeout=30.0) as client:
        data = _get(client, url)
    return data.get("children", [])


def parse_hn_comment(comment: dict) -> RawJobDict | None:
    """Parse an HN comment into a RawJobDict.

    Handles the common HN hiring comment convention:
        Company | Title | Location | Salary | Details | URL

    Short or empty comments are skipped (return None).

    Args:
        comment: HN comment dict with id, text, created_at keys

    Returns:
        RawJobDict if the comment looks like a job post, otherwise None.
    """
    raw_text = comment.get("text", "") or ""

    # Strip HTML (HN stores text as HTML)
    full_text = BeautifulSoup(raw_text, "lxml").get_text(separator=" ").strip()

    if len(full_text) < 20:
        return None

    first_line = full_text.split("\n")[0].strip()

    company: str = ""
    title: str = ""
    location: str | None = None
    salary_raw: str | None = None
    apply_url: str | None = None

    segments = [s.strip() for s in first_line.split("|")]
    if len(segments) >= 2:
        company = segments[0]
        title = segments[1]
        if len(segments) >= 3:
            location = segments[2]
        # Scan remaining segments for salary or URL
        for seg in segments[3:]:
            if _SALARY_RE.search(seg) and salary_raw is None:
                salary_raw = seg
            elif _URL_RE.search(seg) and apply_url is None:
                apply_url = _URL_RE.search(seg).group()  # type: ignore[union-attr]
    else:
        # Non-pipe format: use first line as both company hint and title
        company = first_line[:100]
        title = first_line[:100]

    # Also scan full text for URL if not found in pipe segments
    if apply_url is None:
        url_match = _URL_RE.search(full_text)
        if url_match:
            apply_url = url_match.group()

    return {
        "title": title or first_line[:100],
        "company": company or (first_line.split()[0] if first_line else "Unknown"),
        "description": full_text,
        "source_url": f"https://news.ycombinator.com/item?id={comment['id']}",
        "location_raw": location or None,
        "salary_raw": salary_raw or None,
        "posted_at": comment.get("created_at"),
    }


class HNHiringAdapter:
    """Source adapter for HN Who's Hiring monthly threads.

    Discovers the latest N "Ask HN: Who is Hiring?" threads via the Algolia
    HN Search API, then fetches and parses top-level comments into RawJobDicts.
    Only processes top-level comments (direct replies to the story), skipping
    nested replies.

    The Algolia API is stable and officially provided by HN — this adapter
    is marked fragile=False.

    Attributes:
        source_id: "hn_hiring"
        fragile: False — Algolia API is officially stable for HN search.
    """

    source_id = "hn_hiring"
    fragile = False

    def __init__(self, months_back: int = 1) -> None:
        """Initialize the adapter.

        Args:
            months_back: Number of recent Who's Hiring threads to fetch.
                         Defaults to 1 (latest month only).
        """
        self.months_back = months_back

    def fetch(self) -> list[RawJobDict]:
        """Fetch job posts from HN Who's Hiring threads.

        Process:
        1. Find latest N thread IDs via Algolia search.
        2. For each thread, fetch top-level comments only.
        3. Parse each comment with parse_hn_comment().
        4. Skip None results (meta-comments, very short posts).

        Returns:
            List of RawJobDicts with keys: title, company, description,
            source_url, location_raw, salary_raw, posted_at.
        """
        all_jobs: list[RawJobDict] = []

        try:
            story_ids = find_latest_hn_hiring_threads(months_back=self.months_back)
        except RuntimeError as exc:
            logger.warning("HN hiring thread discovery failed: %s", exc)
            return []

        for story_id in story_ids:
            try:
                comments = fetch_thread_comments(story_id)
            except Exception as exc:
                logger.warning("Failed to fetch HN thread %d: %s — skipping", story_id, exc)
                continue

            for comment in comments:
                try:
                    raw = parse_hn_comment(comment)
                    if raw is not None:
                        all_jobs.append(raw)
                except Exception as exc:
                    logger.debug(
                        "Failed to parse HN comment %s: %s — skipping",
                        comment.get("id"),
                        exc,
                    )

        return all_jobs
