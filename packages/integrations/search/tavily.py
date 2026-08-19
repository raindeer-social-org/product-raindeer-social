import httpx

from packages.integrations.observability import track_integration_call
from packages.integrations.search.base import SearchProvider, SearchResult


class TavilyProvider(SearchProvider):
    """The only file in this codebase allowed to call Tavily directly."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        with track_integration_call("tavily", "search"):
            response = httpx.post(
                self.BASE_URL,
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": max_results,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        return [
            SearchResult(
                title=result["title"],
                url=result["url"],
                content=result.get("content", ""),
            )
            for result in data.get("results", [])
        ]
