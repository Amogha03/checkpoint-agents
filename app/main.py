from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Codebase Analysis Service")


class ResearchRequest(BaseModel):
    repo_url: str
    query: str


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "Codebase Analysis Service is running"}


@app.post("/api/v1/research")
def create_research_job(request: ResearchRequest) -> dict[str, str]:
    return {
        "job_id": str(uuid4()),
        "status": "queued",
    }