from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """The one shape every 4xx/5xx response from this API uses."""

    code: str
    message: str
    details: dict | list | None = None
