from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    dify_configured: bool
