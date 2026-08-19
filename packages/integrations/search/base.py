from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


class SearchProvider(ABC):
    """Interface every search adapter implements. Business/agent code
    must only ever depend on this interface — never import a vendor
    SDK directly outside the adapter that implements it."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...
