import httpx

from packages.integrations.observability import track_integration_call
from packages.integrations.storage.base import StorageProvider


class SupabaseStorageProvider(StorageProvider):
    """The only file allowed to call Supabase Storage directly."""

    def __init__(
        self, base_url: str, service_key: str, bucket: str, timeout: float = 30.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.bucket = bucket
        self.timeout = timeout

    def upload(self, path: str, content: bytes, content_type: str) -> str:
        with track_integration_call("supabase", "storage"):
            response = httpx.post(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
                headers={
                    "Authorization": f"Bearer {self.service_key}",
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
                content=content,
                timeout=self.timeout,
            )
            response.raise_for_status()
        return self.get_url(path)

    def delete(self, path: str) -> None:
        with track_integration_call("supabase", "storage"):
            response = httpx.delete(
                f"{self.base_url}/storage/v1/object/{self.bucket}/{path}",
                headers={"Authorization": f"Bearer {self.service_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()

    def get_url(self, path: str) -> str:
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{path}"
