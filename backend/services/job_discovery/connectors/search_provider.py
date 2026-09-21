from __future__ import annotations

import json
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib import error, parse, request

from backend.core.config import get_settings
from backend.services.job_discovery.base import JobDiscoveryConnectorError

SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str | None = None


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int) -> list[SearchResult]:
        """Return public search results for a query."""


class SerpApiSearchProvider(SearchProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = SERPAPI_SEARCH_URL,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def search(self, query: str, limit: int) -> list[SearchResult]:
        params = parse.urlencode(
            {
                "engine": "google",
                "q": query,
                "num": str(limit),
                "api_key": self.api_key,
            }
        )
        req = request.Request(
            url=f"{self.base_url}?{params}",
            method="GET",
            headers={"Accept": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise JobDiscoveryConnectorError(
                f"Search API request failed with status {exc.code}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise JobDiscoveryConnectorError(
                "Search API timed out. Try again later."
            ) from exc
        except error.URLError as exc:
            raise JobDiscoveryConnectorError(
                "Search API is not reachable right now. Try again later."
            ) from exc
        except json.JSONDecodeError as exc:
            raise JobDiscoveryConnectorError(
                "Search API returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise JobDiscoveryConnectorError("Search API returned an invalid payload.")

        organic_results = payload.get("organic_results")
        if not isinstance(organic_results, list):
            raise JobDiscoveryConnectorError(
                "Search API response did not include organic results."
            )

        results: list[SearchResult] = []
        for item in organic_results:
            if not isinstance(item, dict):
                continue

            title = item.get("title")
            url = item.get("link")
            snippet = item.get("snippet")
            if not isinstance(title, str) or not isinstance(url, str):
                continue

            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet if isinstance(snippet, str) else None,
                )
            )
            if len(results) >= limit:
                break

        return results


def build_search_provider() -> SearchProvider:
    settings = get_settings()
    provider_name = (settings.search_provider or "").strip().lower()
    api_key = (settings.search_api_key or "").strip()

    if not provider_name:
        raise JobDiscoveryConnectorError(
            "Web search is not configured. Set SEARCH_PROVIDER and SEARCH_API_KEY."
        )

    if not api_key:
        raise JobDiscoveryConnectorError(
            "Web search API key is not configured. Set SEARCH_API_KEY."
        )

    if provider_name == "serpapi":
        return SerpApiSearchProvider(
            api_key=api_key,
            base_url=settings.search_api_base_url or SERPAPI_SEARCH_URL,
        )

    raise JobDiscoveryConnectorError(
        f"Unsupported search provider '{settings.search_provider}'."
    )
