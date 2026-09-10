"""FastAPI service layer for asynchronous codebase analysis jobs."""

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.agents.graph import build_codebase_research_graph
from app.agents.state import ResearchState
from app.ingestion import clone_repository, remove_workspace
from app.job_store import JobRecord, JobStore
from app.tools import MCPClientManager, set_mcp_manager

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp_manager: MCPClientManager | None = None
job_store = JobStore()
active_tasks: set[asyncio.Task[None]] = set()


class ResearchRequest(BaseModel):
    """Validated input for a repository research job."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    repo_path: HttpUrl = Field(
        validation_alias=AliasChoices("repo_path", "repo_url"),
        description="Public or authenticated HTTP(S) repository URL.",
    )
    query: str = Field(min_length=3, max_length=2_000)

    @field_validator("repo_path", mode="before")
    @classmethod
    def validate_repo_path(cls, value: object) -> object:
        if value is None or not str(value).strip():
            raise ValueError("repo_path must not be empty")
        return value

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, value: object) -> object:
        if value is None or not str(value).strip():
            raise ValueError("query must not be empty or whitespace-only")
        return value


class JobStatusResponse(BaseModel):
    """Public state of a research job."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    report: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Liveness and MCP initialization status."""

    status: Literal["ok"]
    mcp_connected: bool


def _job_response(record: JobRecord) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=record.job_id,
        status=record.status,
        report=record.report,
        error=record.error,
    )


async def _execute_research(job_id: str, request: ResearchRequest) -> None:
    """Clone and analyze one job, recording every terminal outcome."""
    workspace_path: str | None = None
    job_store.mark_running(job_id)
    try:
        workspace_path = await asyncio.to_thread(
            clone_repository, str(request.repo_path), job_id
        )
        graph = build_codebase_research_graph()
        initial_state: ResearchState = {
            "repo_path": workspace_path,
            "query": request.query,
            "subtasks": [],
            "research_results": [],
            "final_report": "",
            "error_status": "",
        }
        result = await graph.ainvoke(initial_state)
        report = result.get("final_report", "")
        if not report:
            raise RuntimeError("Research completed without a report")
        job_store.mark_done(job_id, report)
    except Exception as exc:
        logger.error("Research job %s failed", job_id, exc_info=True)
        job_store.mark_failed(job_id, f"{type(exc).__name__}: {exc}")
    finally:
        if workspace_path and os.getenv("WORKSPACE_CLEANUP", "true").lower() == "true":
            await asyncio.to_thread(remove_workspace, workspace_path)


def _track_task(task: asyncio.Task[None]) -> None:
    active_tasks.add(task)
    task.add_done_callback(active_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize MCP connections and stop active workers on shutdown."""
    global mcp_manager
    try:
        logger.info("Initializing MCP servers...")
        mcp_manager = MCPClientManager(
            filesystem_root=os.getenv("FILESYSTEM_MCP_ROOT", "/tmp/workspaces"),
            github_token=os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
        )
        await mcp_manager.connect()
        set_mcp_manager(mcp_manager)
        logger.info("MCP servers initialized")
    except Exception:
        logger.exception("MCP initialization failed; research jobs may fail")
        mcp_manager = None

    try:
        yield
    finally:
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        if mcp_manager:
            await mcp_manager.close()
            logger.info("MCP connections closed")


app = FastAPI(title="Codebase Analysis Service", lifespan=lifespan)


def _error_response(error: str, detail: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "detail": detail, "status_code": status_code},
    )


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Log every request outcome without logging request bodies or secrets."""
    started = time.perf_counter()
    job_match = re.search(r"/jobs/([^/]+)$", request.url.path)
    job_id = job_match.group(1) if job_match else None
    tool_error: str | None = None
    response = None
    try:
        response = await call_next(request)
        job_id = job_id or response.headers.get("X-Job-ID")
        return response
    except Exception as exc:
        tool_error = f"{type(exc).__name__}: {exc}"
        request.state.tool_error = tool_error
        raise
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_complete route=%s status=%s duration_ms=%s job_id=%s tool_error=%s",
            request.url.path,
            response.status_code if response else 500,
            duration_ms,
            job_id or "-",
            tool_error or getattr(request.state, "tool_error", "-"),
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return safe, standardized responses for expected HTTP failures."""
    error_names = {
        400: "Bad Request",
        404: "Not Found",
    }
    error = error_names.get(
        exc.status_code,
        "Internal Server Error" if exc.status_code >= 500 else "Bad Request",
    )
    detail = (
        "An unexpected error occurred while processing the request."
        if exc.status_code >= 500
        else exc.detail if isinstance(exc.detail, str) else "Request failed"
    )
    request.state.tool_error = detail if exc.status_code >= 500 else "-"
    return _error_response(error, detail, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Expose malformed payloads as a safe, standardized 400 response."""
    fields = ", ".join(
        str(error.get("loc", ["request"])[-1]) for error in exc.errors()
    )
    detail = f"Invalid request fields: {fields or 'request body'}"
    request.state.tool_error = detail
    return _error_response("Bad Request", detail, status.HTTP_400_BAD_REQUEST)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Hide internal details from clients while preserving server-side diagnostics."""
    logger.exception("Unhandled request exception route=%s", request.url.path)
    request.state.tool_error = type(exc).__name__
    return _error_response(
        "Internal Server Error",
        "An unexpected error occurred while processing the request.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@app.get("/healthz", response_model=HealthResponse)
@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Return liveness and current MCP connection status."""
    connected = bool(
        mcp_manager
        and mcp_manager.filesystem_session
        and mcp_manager.github_session
    )
    return HealthResponse(status="ok", mcp_connected=connected)


@app.post(
    "/research",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@app.post(
    "/api/v1/research",
    response_model=JobStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def research_endpoint(
    request: ResearchRequest, response: Response
) -> JobStatusResponse:
    """Accept a research request and return before clone/analysis completes."""
    job_id = str(uuid4())
    record = job_store.create(job_id)
    response.headers["X-Job-ID"] = job_id
    _track_task(asyncio.create_task(_execute_research(job_id, request)))
    logger.info("Accepted research job %s: %s", job_id, request.query)
    return _job_response(record)


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
@app.get(
    "/api/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    include_in_schema=False,
)
async def get_job(job_id: str) -> JobStatusResponse:
    """Return the current state and report for a known research job."""
    record = job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_response(record)


@app.post("/api/v1/research-sync", response_model=JobStatusResponse)
async def research_sync(
    request: ResearchRequest, response: Response
) -> JobStatusResponse:
    """Run a research job inline for compatibility with the synchronous API."""
    job_id = str(uuid4())
    response.headers["X-Job-ID"] = job_id
    job_store.create(job_id)
    await _execute_research(job_id, request)
    record = job_store.get(job_id)
    if not record:
        raise HTTPException(status_code=500, detail="Research state was lost")
    if record.status == "failed":
        raise HTTPException(
            status_code=500,
            detail="Research failed while processing the repository.",
        )
    return _job_response(record)
