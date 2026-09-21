from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from backend.services.job_discovery.base import (
    JobDiscoveryConnector,
    JobDiscoveryConnectorError,
)
from backend.services.job_discovery.connectors.search_provider import (
    SearchProvider,
    SearchResult,
    build_search_provider,
)
from backend.services.job_discovery.models import (
    DiscoveredJob,
    DiscoverySearchCriteria,
)

DEFAULT_MAX_SEARCH_QUERIES = 5

_SEARCH_ENGINE_LABELS = {
    "duckduckgo",
    "linkedin",
    "indeed",
    "naukri",
    "glassdoor",
    "monster",
    "foundit",
    "jobs",
    "careers",
}

_ROLE_KEYWORDS = {
    "engineer",
    "developer",
    "architect",
    "manager",
    "analyst",
    "scientist",
    "consultant",
    "specialist",
    "administrator",
    "lead",
    "qa",
    "sre",
    "devops",
}

_SENIORITY_KEYWORDS = (
    "principal",
    "staff",
    "lead",
    "senior",
    "sr",
    "junior",
    "jr",
    "mid-level",
    "mid",
)

_PREFERRED_JOB_DOMAINS = (
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
)

_REJECTED_DOMAIN_TOKENS = {
    "duckduckgo",
    "google",
    "bing",
    "yahoo",
    "facebook",
    "instagram",
    "x.com",
    "twitter",
    "medium",
    "substack",
}

_REJECTED_PATH_PATTERNS = (
    "/blog",
    "/blogs",
    "/news",
    "/article",
    "/articles",
    "/press",
    "/insights",
    "/about",
    "/contact",
    "/products",
    "/services",
    "/in/",
    "/company/",
    "/school/",
    "/pub/",
    "/profile/",
    "/profiles/",
    "/people/",
    "/posts/",
)

_JOB_PATH_KEYWORDS = (
    "job",
    "jobs",
    "career",
    "careers",
    "opening",
    "openings",
    "position",
    "positions",
    "vacancy",
    "vacancies",
    "apply",
    "requisition",
    "req",
    "viewjob",
)

_JOB_TITLE_HINTS = (
    "engineer",
    "developer",
    "architect",
    "manager",
    "scientist",
    "analyst",
    "designer",
    "specialist",
    "consultant",
)


class WebSearchConnector(JobDiscoveryConnector):
    source_name = "web_search"
    source_type = "search_result"
    supports_apply = False

    def __init__(
        self,
        limit_per_source: int = 10,
        max_queries: int = DEFAULT_MAX_SEARCH_QUERIES,
        provider: SearchProvider | None = None,
    ) -> None:
        self.limit_per_source = limit_per_source
        self.max_queries = max_queries
        self.provider = provider

    def search(self, criteria: DiscoverySearchCriteria) -> list[DiscoveredJob]:
        queries = _build_search_queries(criteria, max_queries=self.max_queries)
        if not queries:
            raise JobDiscoveryConnectorError(
                "Resume analysis did not contain usable search criteria."
            )

        discovered: list[DiscoveredJob] = []
        seen_urls: set[str] = set()
        provider = self.provider or build_search_provider()

        for query in queries:
            for item in provider.search(query, self.limit_per_source):
                normalized = _normalize_search_result(
                    _search_result_to_payload(item),
                    criteria,
                )
                if normalized is None or normalized.job_url is None:
                    continue
                if normalized.job_url in seen_urls:
                    continue

                seen_urls.add(normalized.job_url)
                discovered.append(normalized)
                if len(discovered) >= self.limit_per_source:
                    return discovered

        return discovered


def _build_search_queries(
    criteria: DiscoverySearchCriteria,
    max_queries: int = DEFAULT_MAX_SEARCH_QUERIES,
) -> list[str]:
    if max_queries <= 0:
        return []

    role_candidates = _extract_role_candidates(criteria)
    if not role_candidates and criteria.skills:
        role_candidates = [criteria.skills[0].strip()]

    seniority = _infer_seniority(criteria, role_candidates)
    top_skills = _dedupe_terms(criteria.skills)[:3]
    location_terms = _build_location_terms(criteria)
    queries: list[str] = []

    if role_candidates:
        queries.append(role_candidates[0])

    primary_base = _strip_seniority(role_candidates[0]) if role_candidates else None
    secondary_base = (
        _strip_seniority(role_candidates[1]) if len(role_candidates) > 1 else None
    )

    if primary_base:
        queries.append(
            _compose_query(primary_base, seniority=seniority, skills=top_skills)
        )
        queries.append(
            _compose_query(
                primary_base,
                seniority=seniority,
                skills=top_skills[:2],
                location_terms=location_terms,
            )
        )
        queries.append(
            _compose_query(
                primary_base,
                seniority=seniority,
                skills=top_skills[:1],
                location_terms=location_terms,
            )
        )

    if secondary_base:
        queries.append(
            _compose_query(
                secondary_base,
                seniority=seniority,
                skills=top_skills[:2],
                location_terms=location_terms,
            )
        )

    for skill in top_skills:
        if primary_base is None:
            break
        queries.append(
            _compose_query(
                f"{skill} {primary_base}",
                seniority=seniority,
                location_terms=location_terms,
            )
        )

    return _dedupe_search_queries(queries, max_queries=max_queries)


def _extract_role_candidates(criteria: DiscoverySearchCriteria) -> list[str]:
    candidates: list[str] = []
    for value in criteria.queries:
        cleaned = _clean_query_phrase(value)
        if not cleaned:
            continue
        if _looks_like_role(cleaned):
            candidates.append(cleaned)
    return _dedupe_terms(candidates)


def _clean_query_phrase(value: str) -> str:
    cleaned = _clean_text(value) or ""
    cleaned = re.sub(r"\bjobs?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|,")
    return cleaned


def _looks_like_role(value: str) -> bool:
    tokens = _tokenize_query(value)
    return any(token in _ROLE_KEYWORDS for token in tokens) or len(tokens) >= 2


def _infer_seniority(
    criteria: DiscoverySearchCriteria,
    role_candidates: list[str],
) -> str | None:
    haystacks = [item.lower() for item in role_candidates]
    for keyword in _SENIORITY_KEYWORDS:
        if any(re.search(rf"\b{re.escape(keyword)}\b", item) for item in haystacks):
            return _format_seniority(keyword)

    years = criteria.years_of_experience
    if years is None:
        return None
    if years >= 10:
        return "Principal"
    if years >= 6:
        return "Senior"
    if years >= 3:
        return "Mid-Level"
    return None


def _format_seniority(value: str) -> str:
    normalized = value.lower()
    if normalized == "sr":
        return "Senior"
    if normalized == "jr":
        return "Junior"
    if normalized == "mid":
        return "Mid-Level"
    return normalized.title()


def _build_location_terms(criteria: DiscoverySearchCriteria) -> list[str]:
    location_terms: list[str] = []
    remote_pref = (criteria.remote_preference or "").strip().lower()
    if remote_pref == "remote":
        location_terms.append("Remote")

    if criteria.location and criteria.location.strip():
        compact = _compact_location(criteria.location)
        if compact:
            location_terms.append(compact)

    return _dedupe_terms(location_terms)


def _compact_location(value: str) -> str | None:
    parts = [item.strip() for item in value.split(",") if item.strip()]
    if not parts:
        return None
    if len(parts) >= 2:
        return parts[-1]
    words = parts[0].split()
    if len(words) <= 3:
        return parts[0]
    return " ".join(words[-2:])


def _compose_query(
    role: str,
    seniority: str | None = None,
    skills: list[str] | None = None,
    location_terms: list[str] | None = None,
) -> str:
    role_text = _clean_query_phrase(role)
    if not role_text:
        return ""

    parts: list[str] = []
    if seniority and seniority.lower() not in role_text.lower():
        parts.append(seniority)
    parts.append(role_text)

    existing_tokens = set(_tokenize_query(" ".join(parts)))
    for skill in skills or []:
        skill_text = _clean_query_phrase(skill)
        if not skill_text:
            continue
        skill_tokens = set(_tokenize_query(skill_text))
        if skill_tokens and skill_tokens.issubset(existing_tokens):
            continue
        parts.append(skill_text)
        existing_tokens.update(skill_tokens)

    for location in location_terms or []:
        location_text = _clean_query_phrase(location)
        if not location_text:
            continue
        location_tokens = set(_tokenize_query(location_text))
        if location_tokens and location_tokens.issubset(existing_tokens):
            continue
        parts.append(location_text)
        existing_tokens.update(location_tokens)

    return " ".join(parts)


def _strip_seniority(value: str) -> str:
    result = value
    for keyword in _SENIORITY_KEYWORDS:
        result = re.sub(
            rf"\b{re.escape(keyword)}\b",
            " ",
            result,
            flags=re.IGNORECASE,
        )
    return re.sub(r"\s+", " ", result).strip()


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = (value or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value.strip())
    return deduped


def _dedupe_search_queries(values: list[str], max_queries: int) -> list[str]:
    deduped: list[str] = []
    token_sets: list[set[str]] = []

    for value in values:
        cleaned = _clean_query_phrase(value)
        if not cleaned:
            continue

        tokens = set(_tokenize_query(cleaned))
        if not tokens:
            continue
        if any(tokens == existing for existing in token_sets):
            continue

        deduped.append(cleaned)
        token_sets.append(tokens)
        if len(deduped) >= max_queries:
            break

    return deduped


def _tokenize_query(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _search_result_to_payload(result: SearchResult) -> dict[str, str]:
    payload = {"title": result.title, "url": result.url}
    if result.snippet is not None:
        payload["snippet"] = result.snippet
    return payload


def _normalize_search_result(
    payload: dict[str, str],
    criteria: DiscoverySearchCriteria,
) -> DiscoveredJob | None:
    raw_title = _clean_text(payload.get("title"))
    job_url = _resolve_search_result_url(payload.get("url"))
    snippet = _clean_text(payload.get("snippet")) or raw_title

    if not raw_title or not job_url or not snippet:
        return None
    if not _is_likely_job_result(job_url, raw_title, snippet):
        return None

    title, company = _infer_title_and_company(raw_title, job_url)
    return DiscoveredJob(
        title=title,
        company=company,
        location=_infer_location(raw_title, snippet, criteria),
        description=snippet,
        job_url=job_url,
        source_name="web_search",
        source_type="search_result",
        discovered_at=datetime.now(UTC),
        source_base_url=None,
        supports_apply=False,
    )


def _resolve_search_result_url(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return None

    if not parsed.netloc:
        return None
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, ""))


def _is_likely_job_result(job_url: str, title: str, snippet: str) -> bool:
    parsed = urlsplit(job_url)
    hostname = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/") or "/"
    title_text = title.lower()
    snippet_text = snippet.lower()
    combined_text = f"{title_text} {snippet_text}"

    if any(token in hostname for token in _REJECTED_DOMAIN_TOKENS):
        return False
    if any(pattern in path for pattern in _REJECTED_PATH_PATTERNS):
        return False

    if _is_linkedin_job_url(hostname, path):
        return True
    if _is_indeed_job_url(hostname, path):
        return True
    if _is_naukri_job_url(hostname, path):
        return True
    if _is_ats_job_url(hostname, path):
        return True

    if any(domain in hostname for domain in _PREFERRED_JOB_DOMAINS):
        return False

    has_job_path = any(keyword in path for keyword in _JOB_PATH_KEYWORDS)
    has_job_text = any(keyword in combined_text for keyword in _JOB_TITLE_HINTS)
    return has_job_path and has_job_text


def _is_linkedin_job_url(hostname: str, path: str) -> bool:
    return "linkedin.com" in hostname and path.startswith("/jobs/view")


def _is_indeed_job_url(hostname: str, path: str) -> bool:
    return "indeed.com" in hostname and (
        path.startswith("/viewjob") or "/jobs/" in path or path.startswith("/jobs")
    )


def _is_naukri_job_url(hostname: str, path: str) -> bool:
    return "naukri.com" in hostname and (
        "job-listings" in path or path.startswith("/job") or "/jobs/" in path
    )


def _is_ats_job_url(hostname: str, path: str) -> bool:
    if "greenhouse.io" in hostname:
        return "/jobs/" in path or path.startswith("/job")
    if "lever.co" in hostname:
        return len(path.strip("/").split("/")) >= 2
    if "ashbyhq.com" in hostname:
        return "/job/" in path or path.startswith("/jobs/")
    return False


def _infer_title_and_company(raw_title: str, job_url: str) -> tuple[str, str]:
    title = raw_title.strip()
    company = _hostname_label(job_url)

    if " at " in raw_title:
        role, company_candidate = raw_title.split(" at ", maxsplit=1)
        role = role.strip()
        company_candidate = company_candidate.strip()
        if role and company_candidate:
            return role, company_candidate

    parts = [
        item.strip() for item in re.split(r"\s+[|\-]\s+", raw_title) if item.strip()
    ]
    if len(parts) >= 2:
        title = parts[0]
        for candidate in parts[1:]:
            normalized = candidate.lower().replace(".com", "").strip()
            if normalized not in _SEARCH_ENGINE_LABELS:
                company = candidate
                break

    return title, company


def _infer_location(
    title: str,
    snippet: str,
    criteria: DiscoverySearchCriteria,
) -> str | None:
    haystack = f"{title} {snippet}".lower()
    if "remote" in haystack:
        return "Remote"
    if criteria.location and criteria.location.strip().lower() in haystack:
        return criteria.location.strip()
    return None


def _hostname_label(url: str) -> str:
    hostname = urlsplit(url).netloc.lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    parts = [item for item in hostname.split(".") if item]
    if not parts:
        return "Unknown company"
    return parts[0].replace("-", " ").title()


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None
