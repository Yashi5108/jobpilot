import json
import socket

import pytest

from backend.services.job_discovery.base import JobDiscoveryConnectorError
from backend.services.job_discovery.connectors.remotive import _normalize_job
from backend.services.job_discovery.connectors.search_provider import (
    SearchResult,
    SerpApiSearchProvider,
    build_search_provider,
)
from backend.services.job_discovery.connectors.web_search import (
    WebSearchConnector,
    _build_search_queries,
    _is_likely_job_result,
    _normalize_search_result,
)
from backend.services.job_discovery.models import DiscoverySearchCriteria


def test_remotive_normalization_maps_public_api_fields() -> None:
    job = _normalize_job(
        {
            "id": 123,
            "title": "Backend Engineer",
            "company_name": "Acme",
            "candidate_required_location": "Remote",
            "description": "<p>Build APIs with Python.</p>",
            "url": "https://example.com/jobs/backend-engineer",
            "publication_date": "2026-09-21T10:00:00+00:00",
        }
    )

    assert job is not None
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert job.description == "Build APIs with Python."
    assert job.job_url == "https://example.com/jobs/backend-engineer"
    assert job.external_id == "123"


def test_web_search_normalization_maps_public_result_fields() -> None:
    criteria = DiscoverySearchCriteria(
        queries=["Backend Engineer"],
        skills=["Python"],
        location="Bengaluru",
        remote_preference="remote",
    )

    job = _normalize_search_result(
        {
            "title": "Backend Engineer - Acme - LinkedIn",
            "url": "https://www.linkedin.com/jobs/view/123",
            "snippet": "Remote backend engineering role using Python and FastAPI.",
        },
        criteria,
    )

    assert job is not None
    assert job.title == "Backend Engineer"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert (
        job.description == "Remote backend engineering role using Python and FastAPI."
    )
    assert job.job_url == "https://www.linkedin.com/jobs/view/123"
    assert job.source_name == "web_search"
    assert job.source_type == "search_result"
    assert job.supports_apply is False


def test_build_search_provider_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "")
    monkeypatch.setenv("SEARCH_API_KEY", "")

    from backend.core.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(JobDiscoveryConnectorError, match="not configured"):
            build_search_provider()
    finally:
        get_settings.cache_clear()


def test_build_search_provider_uses_serpapi_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_PROVIDER", "serpapi")
    monkeypatch.setenv("SEARCH_API_KEY", "secret-key")
    monkeypatch.setenv("SEARCH_API_BASE_URL", "https://example.test/search.json")

    from backend.core.config import get_settings

    get_settings.cache_clear()
    try:
        provider = build_search_provider()
    finally:
        get_settings.cache_clear()

    assert isinstance(provider, SerpApiSearchProvider)
    assert provider.api_key == "secret-key"
    assert provider.base_url == "https://example.test/search.json"


def test_serpapi_search_provider_maps_mocked_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "organic_results": [
                        {
                            "title": "Backend Engineer - Acme",
                            "link": "https://careers.acme.com/jobs/backend-engineer",
                            "snippet": "Remote backend engineering role.",
                        },
                        {"title": "Ignore missing link"},
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "backend.services.job_discovery.connectors.search_provider.request.urlopen",
        lambda req, timeout=15: _Response(),
    )

    provider = SerpApiSearchProvider(
        api_key="secret-key",
        base_url="https://example.test/search.json",
    )
    results = provider.search("Backend Engineer", 10)

    assert results == [
        SearchResult(
            title="Backend Engineer - Acme",
            url="https://careers.acme.com/jobs/backend-engineer",
            snippet="Remote backend engineering role.",
        )
    ]


def test_serpapi_search_provider_converts_timeout_to_connector_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_timeout(req, timeout=15):
        raise socket.timeout("timed out")

    monkeypatch.setattr(
        "backend.services.job_discovery.connectors.search_provider.request.urlopen",
        _raise_timeout,
    )

    provider = SerpApiSearchProvider(
        api_key="secret-key",
        base_url="https://example.test/search.json",
    )

    with pytest.raises(JobDiscoveryConnectorError, match="timed out"):
        provider.search("Backend Engineer", 10)


@pytest.mark.parametrize(
    ("job_url", "title", "snippet"),
    [
        (
            "https://www.linkedin.com/jobs/view/123",
            "Backend Engineer - Acme - LinkedIn",
            "Remote backend engineering role.",
        ),
        (
            "https://www.naukri.com/job-listings-senior-backend-engineer-acme-123",
            "Senior Backend Engineer - Naukri",
            "Apply for backend engineer role.",
        ),
        (
            "https://www.indeed.com/viewjob?jk=123",
            "Backend Engineer - Indeed",
            "Hiring Python backend engineer.",
        ),
        (
            "https://boards.greenhouse.io/acme/jobs/12345",
            "Backend Engineer - Acme",
            "Acme careers opening.",
        ),
        (
            "https://jobs.lever.co/acme/12345",
            "Backend Engineer - Acme",
            "Apply to Acme.",
        ),
        (
            "https://jobs.ashbyhq.com/acme/job/12345",
            "Backend Engineer - Acme",
            "Ashby hosted job.",
        ),
        (
            "https://careers.example.com/jobs/backend-engineer",
            "Backend Engineer - Example",
            "Company careers role for backend engineer.",
        ),
    ],
)
def test_is_likely_job_result_accepts_job_patterns(
    job_url: str,
    title: str,
    snippet: str,
) -> None:
    assert _is_likely_job_result(job_url, title, snippet) is True


@pytest.mark.parametrize(
    ("job_url", "title", "snippet"),
    [
        (
            "https://duckduckgo.com/?q=backend+engineer",
            "Search results",
            "Search engine result page.",
        ),
        (
            "https://example.com/blog/how-we-hire-engineers",
            "Engineering hiring blog",
            "A blog article.",
        ),
        (
            "https://example.com/news/company-funding-round",
            "Company raises funding",
            "News article about the company.",
        ),
        (
            "https://example.com/",
            "Acme Home",
            "Welcome to Acme.",
        ),
        (
            "https://www.linkedin.com/in/some-person",
            "Some Person - LinkedIn",
            "Profile page.",
        ),
        (
            "https://www.linkedin.com/company/acme",
            "Acme - LinkedIn",
            "Company page.",
        ),
    ],
)
def test_is_likely_job_result_rejects_irrelevant_patterns(
    job_url: str,
    title: str,
    snippet: str,
) -> None:
    assert _is_likely_job_result(job_url, title, snippet) is False


def test_web_search_normalization_rejects_non_job_pages() -> None:
    criteria = DiscoverySearchCriteria(
        queries=["Backend Engineer"],
        skills=["Python"],
        location="Bengaluru",
        remote_preference="remote",
    )

    job = _normalize_search_result(
        {
            "title": "Engineering Blog - Acme",
            "url": "https://example.com/blog/backend-engineering",
            "snippet": "Read our backend engineering article.",
        },
        criteria,
    )

    assert job is None


def test_web_search_connector_uses_resume_queries_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    criteria = DiscoverySearchCriteria(
        queries=["Senior Backend Engineer", "Python Developer"],
        skills=["Python", "FastAPI"],
        location="Bengaluru",
        remote_preference="remote",
        limit_per_source=2,
    )
    requested_queries: list[str] = []

    class _Provider:
        def search(self, query: str, limit: int) -> list[SearchResult]:
            requested_queries.append(query)
            return [
                SearchResult(
                    title="Backend Engineer - Acme Careers",
                    url="https://example.com/jobs/backend-engineer",
                    snippet="Remote Python platform role.",
                ),
                SearchResult(
                    title="Backend Engineer - Acme Careers",
                    url="https://example.com/jobs/backend-engineer",
                    snippet="Remote Python platform role.",
                ),
                SearchResult(
                    title="Platform Engineer | Example Org",
                    url="https://careers.example.org/jobs/platform",
                    snippet="Bengaluru platform engineering job.",
                ),
            ]

    connector = WebSearchConnector(limit_per_source=2, provider=_Provider())
    jobs = connector.search(criteria)

    assert requested_queries == ["Senior Backend Engineer"]
    assert len(jobs) == 2
    assert jobs[0].job_url == "https://example.com/jobs/backend-engineer"
    assert jobs[1].company == "Example Org"


def test_web_search_connector_surfaces_provider_error() -> None:
    criteria = DiscoverySearchCriteria(
        queries=["Senior Backend Engineer"],
        skills=["Python"],
        location="Bengaluru",
        remote_preference="remote",
    )

    class _BrokenProvider:
        def search(self, query: str, limit: int) -> list[SearchResult]:
            raise JobDiscoveryConnectorError("Web search is not configured.")

    connector = WebSearchConnector(limit_per_source=2, provider=_BrokenProvider())

    with pytest.raises(JobDiscoveryConnectorError, match="not configured"):
        connector.search(criteria)


def test_build_search_queries_generates_ranked_variants() -> None:
    queries = _build_search_queries(
        DiscoverySearchCriteria(
            queries=[
                "Senior Python Backend Engineer",
                "Backend Engineer",
                "Senior Backend Engineer",
            ],
            skills=["Python", "FastAPI", "AWS"],
            location="Bengaluru, India",
            remote_preference="remote",
            years_of_experience=8,
        )
    )

    assert 3 <= len(queries) <= 5
    assert queries[0] == "Senior Python Backend Engineer"
    assert any("FastAPI" in item and "AWS" in item for item in queries)
    assert any("Remote" in item for item in queries)
    assert any("India" in item for item in queries)
    assert all("jobs" not in item.lower() for item in queries)


def test_build_search_queries_deduplicates_near_duplicates_and_honors_max() -> None:
    queries = _build_search_queries(
        DiscoverySearchCriteria(
            queries=[
                "Senior Backend Engineer",
                "Backend Engineer Senior",
                "Senior Backend Engineer",
                "Backend Engineer",
            ],
            skills=["Python", "Python", "AWS", "FastAPI"],
            location="Pune, India",
            remote_preference="remote",
            years_of_experience=7,
        ),
        max_queries=3,
    )

    assert len(queries) == 3
    assert queries[0] == "Senior Backend Engineer"
    assert len({frozenset(item.lower().split()) for item in queries}) == len(queries)
    assert any("Python" in item for item in queries)
    assert any("Remote" in item or "India" in item for item in queries)
