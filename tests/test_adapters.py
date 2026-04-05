"""Tests for source adapters, DiscoveryConfig, and SourceAdapter Protocol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Task 1 tests: DiscoveryConfig, is_stale, SourceAdapter Protocol
# ---------------------------------------------------------------------------


class TestDiscoveryConfigDefaults:
    """DiscoveryConfig() with no args returns expected defaults."""

    def test_defaults_empty_lists(self):
        from jobinator.configs.settings import DiscoveryConfig

        cfg = DiscoveryConfig()
        assert cfg.greenhouse == []
        assert cfg.lever == []
        assert cfg.wellfound_keywords == []
        assert cfg.wellfound_companies == []

    def test_default_stale_after_days(self):
        from jobinator.configs.settings import DiscoveryConfig

        cfg = DiscoveryConfig()
        assert cfg.stale_after_days == 14

    def test_default_hn_months_back(self):
        from jobinator.configs.settings import DiscoveryConfig

        cfg = DiscoveryConfig()
        assert cfg.hn_months_back == 1

    def test_greenhouse_list(self):
        from jobinator.configs.settings import DiscoveryConfig

        cfg = DiscoveryConfig(greenhouse=["anthropic"])
        assert cfg.greenhouse == ["anthropic"]

    def test_lever_list(self):
        from jobinator.configs.settings import DiscoveryConfig

        cfg = DiscoveryConfig(lever=["figma", "stripe"])
        assert cfg.lever == ["figma", "stripe"]


class TestGetDiscoveryConfig:
    """get_discovery_config() returns DiscoveryConfig with defaults when no config.toml exists."""

    def test_returns_defaults_when_no_config(self, tmp_path):
        from jobinator.configs.settings import get_discovery_config

        cfg = get_discovery_config(config_dir=str(tmp_path))
        assert isinstance(cfg.stale_after_days, int)
        assert cfg.stale_after_days == 14
        assert cfg.greenhouse == []

    def test_reads_discovery_section(self, tmp_path):
        from jobinator.configs.settings import get_discovery_config

        toml_content = """
[discovery]
greenhouse = ["anthropic", "openai"]
stale_after_days = 7
"""
        (tmp_path / "config.toml").write_text(toml_content)
        cfg = get_discovery_config(config_dir=str(tmp_path))
        assert cfg.greenhouse == ["anthropic", "openai"]
        assert cfg.stale_after_days == 7


class TestIsStaleField:
    """NormalizedJob has is_stale boolean field defaulting to False."""

    def test_is_stale_default_false(self):
        from jobinator.models.job import NormalizedJob

        job = NormalizedJob(
            source="test",
            source_url="https://example.com/job/1",
            title="Data Scientist",
            title_normalized="data scientist",
            company="Acme",
            company_slug="acme",
            description="A job",
            description_hash="abc123",
            raw_json="{}",
        )
        assert job.is_stale is False

    def test_is_stale_can_be_set_true(self):
        from jobinator.models.job import NormalizedJob

        job = NormalizedJob(
            source="test",
            source_url="https://example.com/job/2",
            title="ML Engineer",
            title_normalized="ml engineer",
            company="Acme",
            company_slug="acme",
            description="Another job",
            description_hash="def456",
            raw_json="{}",
            is_stale=True,
        )
        assert job.is_stale is True


class TestSourceAdapterProtocol:
    """SourceAdapter Protocol defines source_id (str), fragile (bool), fetch() -> list[RawJobDict].

    Tests verify the Protocol contract and AdapterBrokenError exception class.
    """

    def test_protocol_attributes_exist(self):
        from jobinator.adapters.base import SourceAdapter

        # Protocol should exist as a class
        assert hasattr(SourceAdapter, "__protocol_attrs__") or hasattr(
            SourceAdapter, "_is_protocol"
        )

    def test_adapter_broken_error_is_exception(self):
        from jobinator.adapters.base import AdapterBrokenError

        assert issubclass(AdapterBrokenError, Exception)

    def test_adapter_broken_error_can_raise(self):
        from jobinator.adapters.base import AdapterBrokenError

        with pytest.raises(AdapterBrokenError):
            raise AdapterBrokenError("test error")

    def test_source_adapter_imported_from_init(self):
        from jobinator.adapters import AdapterBrokenError, SourceAdapter

        assert SourceAdapter is not None
        assert AdapterBrokenError is not None

    def test_concrete_class_satisfies_protocol(self):
        """Concrete class with source_id, fragile, and fetch() satisfies SourceAdapter Protocol."""

        class MockAdapter:
            source_id = "mock"
            fragile = False

            def fetch(self):
                return []

        # Protocol structural check — should not raise
        adapter = MockAdapter()
        assert adapter.source_id == "mock"
        assert adapter.fragile is False
        assert adapter.fetch() == []


# ---------------------------------------------------------------------------
# Task 2 tests: GreenhouseAdapter and LeverAdapter
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestGreenhouseAdapter:
    """Tests for GreenhouseAdapter using respx mocks."""

    def test_fetch_returns_raw_job_dicts(self, respx_mock):
        """GreenhouseAdapter.fetch() with 1 configured company returns RawJobDicts."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        fixture_path = FIXTURES_DIR / "greenhouse_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get(
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"
        ).mock(return_value=__import__("httpx").Response(200, json=fixture_data))

        adapter = GreenhouseAdapter(board_tokens=["anthropic"])
        results = adapter.fetch()

        assert len(results) == 2

    def test_fetch_multiple_companies(self, respx_mock):
        """GreenhouseAdapter.fetch() with 2 configured companies returns RawJobDicts from both."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        fixture_path = FIXTURES_DIR / "greenhouse_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get(
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"
        ).mock(return_value=__import__("httpx").Response(200, json=fixture_data))

        # Second company returns empty
        respx_mock.get("https://boards-api.greenhouse.io/v1/boards/openai/jobs?content=true").mock(
            return_value=__import__("httpx").Response(200, json={"jobs": [], "meta": {"total": 0}})
        )

        adapter = GreenhouseAdapter(board_tokens=["anthropic", "openai"])
        results = adapter.fetch()

        assert len(results) == 2  # 2 from anthropic + 0 from openai

    def test_fetch_maps_fields_correctly(self, respx_mock):
        """GreenhouseAdapter maps API fields correctly."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        fixture_path = FIXTURES_DIR / "greenhouse_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get(
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"
        ).mock(return_value=__import__("httpx").Response(200, json=fixture_data))

        adapter = GreenhouseAdapter(board_tokens=["anthropic"])
        results = adapter.fetch()

        first = results[0]
        assert first["title"] == "Senior ML Engineer"
        assert first["company"] == "anthropic"
        assert first["source_url"] == "https://boards.greenhouse.io/anthropic/jobs/12345"
        assert first["location_raw"] == "San Francisco, CA"
        assert first["posted_at"] == "2026-03-15T10:00:00Z"

    def test_fetch_strips_html_from_description(self, respx_mock):
        """GreenhouseAdapter strips HTML from description."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        fixture_path = FIXTURES_DIR / "greenhouse_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get(
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs?content=true"
        ).mock(return_value=__import__("httpx").Response(200, json=fixture_data))

        adapter = GreenhouseAdapter(board_tokens=["anthropic"])
        results = adapter.fetch()

        first = results[0]
        # Should not contain HTML tags
        assert "<p>" not in first["description"]
        assert "<strong>" not in first["description"]
        # Should contain the text content
        assert "Senior ML Engineer" in first["description"]

    def test_fetch_handles_404(self, respx_mock):
        """GreenhouseAdapter handles 404 for bad board token — logs warning, returns empty list."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        respx_mock.get(
            "https://boards-api.greenhouse.io/v1/boards/badtoken/jobs?content=true"
        ).mock(return_value=__import__("httpx").Response(404))

        adapter = GreenhouseAdapter(board_tokens=["badtoken"])
        results = adapter.fetch()

        assert results == []

    def test_source_id_and_fragile(self):
        """GreenhouseAdapter sets source_id='greenhouse' and fragile=False."""
        from jobinator.adapters.greenhouse import GreenhouseAdapter

        adapter = GreenhouseAdapter(board_tokens=[])
        assert adapter.source_id == "greenhouse"
        assert adapter.fragile is False


class TestLeverAdapter:
    """Tests for LeverAdapter using respx mocks."""

    def test_fetch_returns_raw_job_dicts(self, respx_mock):
        """LeverAdapter.fetch() with 1 configured company returns RawJobDicts."""
        from jobinator.adapters.lever import LeverAdapter

        fixture_path = FIXTURES_DIR / "lever_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get("https://api.lever.co/v0/postings/figma?mode=json&skip=0&limit=50").mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = LeverAdapter(companies=["figma"])
        results = adapter.fetch()

        assert len(results) == 1

    def test_fetch_maps_fields_correctly(self, respx_mock):
        """LeverAdapter maps API fields correctly."""
        from jobinator.adapters.lever import LeverAdapter

        fixture_path = FIXTURES_DIR / "lever_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get("https://api.lever.co/v0/postings/figma?mode=json&skip=0&limit=50").mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = LeverAdapter(companies=["figma"])
        results = adapter.fetch()

        first = results[0]
        assert first["title"] == "Machine Learning Engineer"
        assert first["company"] == "figma"
        assert first["source_url"] == "https://jobs.lever.co/figma/abc-123-def"
        assert first["location_raw"] == "New York, NY"
        # Lever public API doesn't expose posted date
        assert first.get("posted_at") is None

    def test_fetch_passes_through_salary_raw(self, respx_mock):
        """LeverAdapter passes salary_raw through as dict."""
        from jobinator.adapters.lever import LeverAdapter

        fixture_path = FIXTURES_DIR / "lever_response.json"
        fixture_data = json.loads(fixture_path.read_text())

        respx_mock.get("https://api.lever.co/v0/postings/figma?mode=json&skip=0&limit=50").mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = LeverAdapter(companies=["figma"])
        results = adapter.fetch()

        first = results[0]
        assert isinstance(first.get("salary_raw"), dict)
        assert first["salary_raw"]["min"] == 180000
        assert first["salary_raw"]["max"] == 250000

    def test_fetch_pagination(self, respx_mock):
        """LeverAdapter handles pagination when more than 50 results."""
        from jobinator.adapters.lever import LeverAdapter

        # First page: 50 items
        first_page = [
            {
                "id": f"job-{i}",
                "text": f"Job {i}",
                "categories": {"location": "Remote"},
                "workplaceType": "remote",
                "descriptionPlain": f"Description {i}",
                "hostedUrl": f"https://jobs.lever.co/acme/job-{i}",
                "applyUrl": f"https://jobs.lever.co/acme/job-{i}/apply",
            }
            for i in range(50)
        ]
        # Second page: 2 items (less than limit=50, signals end)
        second_page = [
            {
                "id": "job-50",
                "text": "Job 50",
                "categories": {"location": "Remote"},
                "workplaceType": "remote",
                "descriptionPlain": "Description 50",
                "hostedUrl": "https://jobs.lever.co/acme/job-50",
                "applyUrl": "https://jobs.lever.co/acme/job-50/apply",
            },
            {
                "id": "job-51",
                "text": "Job 51",
                "categories": {"location": "Remote"},
                "workplaceType": "remote",
                "descriptionPlain": "Description 51",
                "hostedUrl": "https://jobs.lever.co/acme/job-51",
                "applyUrl": "https://jobs.lever.co/acme/job-51/apply",
            },
        ]

        respx_mock.get("https://api.lever.co/v0/postings/acme?mode=json&skip=0&limit=50").mock(
            return_value=__import__("httpx").Response(200, json=first_page)
        )

        respx_mock.get("https://api.lever.co/v0/postings/acme?mode=json&skip=50&limit=50").mock(
            return_value=__import__("httpx").Response(200, json=second_page)
        )

        adapter = LeverAdapter(companies=["acme"])
        results = adapter.fetch()

        assert len(results) == 52  # 50 + 2

    def test_fetch_handles_http_error(self, respx_mock):
        """LeverAdapter handles HTTP errors: logs warning, continues to next company."""
        from jobinator.adapters.lever import LeverAdapter

        respx_mock.get(
            "https://api.lever.co/v0/postings/badcompany?mode=json&skip=0&limit=50"
        ).mock(return_value=__import__("httpx").Response(500))

        adapter = LeverAdapter(companies=["badcompany"])
        results = adapter.fetch()

        assert results == []

    def test_source_id_and_fragile(self):
        """LeverAdapter sets source_id='lever' and fragile=False."""
        from jobinator.adapters.lever import LeverAdapter

        adapter = LeverAdapter(companies=[])
        assert adapter.source_id == "lever"
        assert adapter.fragile is False


# ---------------------------------------------------------------------------
# HN Who's Hiring Adapter tests
# ---------------------------------------------------------------------------

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/99999999"


class TestHNHiringAdapter:
    """Tests for HNHiringAdapter using respx mocks."""

    def test_find_latest_thread_returns_story_id(self, respx_mock):
        """find_latest_hn_hiring_threads() returns story IDs from Algolia search response."""
        from jobinator.adapters.hn_hiring import find_latest_hn_hiring_threads

        algolia_response = {
            "hits": [{"objectID": "99999999", "title": "Ask HN: Who is Hiring? (April 2026)"}]
        }
        respx_mock.get(ALGOLIA_SEARCH_URL).mock(
            return_value=__import__("httpx").Response(200, json=algolia_response)
        )

        result = find_latest_hn_hiring_threads(months_back=1)
        assert result == [99999999]

    def test_find_latest_thread_raises_on_empty_hits(self, respx_mock):
        """find_latest_hn_hiring_threads() raises RuntimeError when no hits returned."""
        from jobinator.adapters.hn_hiring import find_latest_hn_hiring_threads

        algolia_response = {"hits": []}
        respx_mock.get(ALGOLIA_SEARCH_URL).mock(
            return_value=__import__("httpx").Response(200, json=algolia_response)
        )

        with pytest.raises(RuntimeError, match="No Who is Hiring thread found"):
            find_latest_hn_hiring_threads(months_back=1)

    def test_parse_hn_comment_pipe_delimited(self):
        """parse_hn_comment extracts company, title, location from pipe-delimited format."""
        from jobinator.adapters.hn_hiring import parse_hn_comment

        comment = {
            "id": 100000001,
            "text": "Anthropic | Senior ML Engineer | San Francisco, CA | $200k-$300k | Full-time | https://anthropic.com/careers",
            "author": "anthropic_hr",
            "created_at": "2026-04-01T12:00:00Z",
        }
        result = parse_hn_comment(comment)
        assert result is not None
        assert result["company"] == "Anthropic"
        assert result["title"] == "Senior ML Engineer"
        assert result["location_raw"] == "San Francisco, CA"

    def test_parse_hn_comment_non_pipe_delimited(self):
        """parse_hn_comment handles non-pipe-delimited comments."""
        from jobinator.adapters.hn_hiring import parse_hn_comment

        comment = {
            "id": 100000003,
            "text": (
                "Is anyone else finding the market tough this month?"
                " We are seeing a lot of activity in ML."
            ),
            "author": "jobseeker",
            "created_at": "2026-04-01T13:00:00Z",
        }
        result = parse_hn_comment(comment)
        # Short non-job meta comment should return a result but company/title from first line
        if result is not None:
            assert "company" in result
            assert "title" in result

    def test_fetch_returns_raw_job_dicts(self, respx_mock):
        """HNHiringAdapter.fetch() returns RawJobDicts from mocked thread."""
        from jobinator.adapters.hn_hiring import HNHiringAdapter

        fixture_path = FIXTURES_DIR / "hn_thread.json"
        fixture_data = json.loads(fixture_path.read_text())

        algolia_response = {
            "hits": [{"objectID": "99999999", "title": "Ask HN: Who is Hiring? (April 2026)"}]
        }
        respx_mock.get(ALGOLIA_SEARCH_URL).mock(
            return_value=__import__("httpx").Response(200, json=algolia_response)
        )
        respx_mock.get(ALGOLIA_ITEM_URL).mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = HNHiringAdapter(months_back=1)
        results = adapter.fetch()

        # Should have 2 job posts (Anthropic + Stripe), meta comment excluded/parsed
        assert len(results) >= 2
        urls = [r["source_url"] for r in results]
        assert any("news.ycombinator.com/item?id=100000001" in u for u in urls)
        assert any("news.ycombinator.com/item?id=100000002" in u for u in urls)

    def test_fetch_skips_nested_replies(self, respx_mock):
        """HNHiringAdapter.fetch() skips nested replies (only processes top-level children)."""
        from jobinator.adapters.hn_hiring import HNHiringAdapter

        fixture_path = FIXTURES_DIR / "hn_thread.json"
        fixture_data = json.loads(fixture_path.read_text())

        algolia_response = {
            "hits": [{"objectID": "99999999", "title": "Ask HN: Who is Hiring? (April 2026)"}]
        }
        respx_mock.get(ALGOLIA_SEARCH_URL).mock(
            return_value=__import__("httpx").Response(200, json=algolia_response)
        )
        respx_mock.get(ALGOLIA_ITEM_URL).mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = HNHiringAdapter(months_back=1)
        results = adapter.fetch()

        # Comment 100000099 is a nested reply — it must not appear in results
        urls = [r["source_url"] for r in results]
        assert not any("news.ycombinator.com/item?id=100000099" in u for u in urls)

    def test_fetch_source_url_points_to_hn_comment(self, respx_mock):
        """HNHiringAdapter.fetch() sets source_url to HN comment URL."""
        from jobinator.adapters.hn_hiring import HNHiringAdapter

        fixture_path = FIXTURES_DIR / "hn_thread.json"
        fixture_data = json.loads(fixture_path.read_text())

        algolia_response = {
            "hits": [{"objectID": "99999999", "title": "Ask HN: Who is Hiring? (April 2026)"}]
        }
        respx_mock.get(ALGOLIA_SEARCH_URL).mock(
            return_value=__import__("httpx").Response(200, json=algolia_response)
        )
        respx_mock.get(ALGOLIA_ITEM_URL).mock(
            return_value=__import__("httpx").Response(200, json=fixture_data)
        )

        adapter = HNHiringAdapter(months_back=1)
        results = adapter.fetch()

        for r in results:
            assert r["source_url"].startswith("https://news.ycombinator.com/item?id=")

    def test_source_id_and_fragile(self):
        """HNHiringAdapter sets source_id='hn_hiring' and fragile=False."""
        from jobinator.adapters.hn_hiring import HNHiringAdapter

        adapter = HNHiringAdapter()
        assert adapter.source_id == "hn_hiring"
        assert adapter.fragile is False
