from abc import ABC, abstractmethod


class StorageProvider(ABC):
    """Interface every storage adapter implements. Business/agent code
    must only ever depend on this interface — never import a vendor SDK
    directly outside the adapter that implements it."""

    @abstractmethod
    def upload(self, path: str, content: bytes, content_type: str) -> str:
        """Uploads content at path, returns a retrievable URL."""

    @abstractmethod
    def delete(self, path: str) -> None:
        ...

    @abstractmethod
    def get_url(self, path: str) -> str:
        ...
