import httpx

from packages.integrations.image_gen.base import ImageProvider, ImageResult
from packages.integrations.observability import track_integration_call


class FalImageProvider(ImageProvider):
    """The only file allowed to call fal.ai directly (Issue #22). Every
    other module — including generation_engine.py's media hook — must
    reach fal.ai only through the ImageProvider interface
    (packages/integrations/image_gen/base.py), resolved via
    packages.integrations.registry.get_image_provider(), same
    interface-only contract every other adapter in this package follows.
    """

    # fal.ai's synchronous inference endpoint — one HTTP call in, one
    # generated image out. Model id is configurable (constructor arg) so a
    # different fal model can be swapped in via settings without touching
    # this adapter's request/response handling.
    BASE_URL = "https://fal.run"
    DEFAULT_MODEL = "fal-ai/flux/dev"

    def __init__(
        self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 60.0
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, **kwargs: object) -> ImageResult:
        with track_integration_call("fal", "image_gen"):
            response = httpx.post(
                f"{self.BASE_URL}/{self.model}",
                headers={"Authorization": f"Key {self.api_key}"},
                json={"prompt": prompt, **kwargs},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

        images = data.get("images") or []
        if not images or not images[0].get("url"):
            raise ValueError("fal.ai response contained no generated image URL")
        return ImageResult(url=images[0]["url"])
