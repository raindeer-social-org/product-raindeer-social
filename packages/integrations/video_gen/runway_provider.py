"""RunwayProvider — Issue #23's real VideoProvider adapter, the only file
allowed to call Runway's API directly (same "one adapter, one vendor"
convention as every other packages/integrations/*/*.py provider — see
packages/integrations/llm/openrouter_provider.py, packages/integrations/
storage/supabase_provider.py).

Runway's generation API is asynchronous: submitting a prompt returns a
task id immediately, and the caller polls a status endpoint until the
task finishes (docs.dev.runwayml.com). This adapter hides that whole
create -> poll -> fetch sequence behind the single synchronous
VideoProvider.generate() call, so callers (generation_engine.py) never
see Runway's task/polling shape — only VideoResult.

`generate()` also downloads the finished asset's bytes itself (rather
than just returning Runway's own hosted URL) since that URL is not
guaranteed to stay valid indefinitely; the caller re-uploads
`VideoResult.content` to this repo's own StorageProvider
(packages/integrations/storage) for a durable link. The whole
create+poll+download sequence is wrapped in one track_integration_call
context (same pattern every other adapter uses to log to
integration_calls) since, from a caller's perspective, it's one logical
"generate a video" call — not several independent vendor calls.
"""

import time

import httpx

from packages.integrations.observability import track_integration_call
from packages.integrations.video_gen.base import VideoProvider, VideoResult


class RunwayProvider(VideoProvider):
    """The only file allowed to call Runway's API directly."""

    BASE_URL = "https://api.runwayml.com"
    API_VERSION = "2024-11-06"

    def __init__(
        self,
        api_key: str,
        timeout: float = 60.0,
        poll_interval: float = 2.0,
        max_poll_attempts: int = 30,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Runway-Version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, **kwargs: object) -> VideoResult:
        """Submits a text-to-video generation task, polls until it
        completes (or fails/times out), then downloads the resulting
        asset. `kwargs` accepts optional `model`/`ratio`/`duration`
        overrides — sensible defaults are used otherwise, since callers
        (generation_engine.py) only ever pass a prompt."""
        model = str(kwargs.get("model") or "gen3a_turbo")
        ratio = str(kwargs.get("ratio") or "1280:720")
        duration = kwargs.get("duration") or 5

        with track_integration_call("runway", "video"):
            create_response = httpx.post(
                f"{self.BASE_URL}/v1/text_to_video",
                headers=self._headers(),
                json={
                    "model": model,
                    "promptText": prompt,
                    "ratio": ratio,
                    "duration": duration,
                },
                timeout=self.timeout,
            )
            create_response.raise_for_status()
            task_id = create_response.json()["id"]

            output_url = self._poll_until_complete(task_id)

            asset_response = httpx.get(output_url, timeout=self.timeout)
            asset_response.raise_for_status()
            content = asset_response.content
            content_type = asset_response.headers.get("content-type", "video/mp4")

        return VideoResult(url=output_url, content=content, content_type=content_type)

    def _poll_until_complete(self, task_id: str) -> str:
        for _ in range(self.max_poll_attempts):
            response = httpx.get(
                f"{self.BASE_URL}/v1/tasks/{task_id}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            status = data.get("status")

            if status == "SUCCEEDED":
                output = data.get("output") or []
                if not output:
                    raise RuntimeError(
                        f"Runway task {task_id} succeeded but returned no output"
                    )
                return output[0]
            if status == "FAILED":
                raise RuntimeError(
                    f"Runway task {task_id} failed: {data.get('failure') or 'unknown error'}"
                )

            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"Runway task {task_id} did not complete within {self.max_poll_attempts} poll attempts"
        )
