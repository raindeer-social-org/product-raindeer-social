from fastapi import FastAPI

from apps.api.config import get_settings

settings = get_settings()

app = FastAPI(title="Raindeer Social API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
