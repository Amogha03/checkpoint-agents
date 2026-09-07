"""
Main FastAPI application for the Codebase Analysis Service.
Provides REST endpoints for research job submission and result retrieval.
Integrates Phase 3 MCP tool support for dynamic codebase analysis.
"""

import logging
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agents.graph import build_codebase_research_graph
from app.agents.state import ResearchState
from app.ingestion import clone_repository, remove_workspace
from app.tools import MCPClientManager, set_mcp_manager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global MCP manager (initialized on startup)
mcp_manager: MCPClientManager = None


class ResearchRequest(BaseModel):
    repo_path: str
    query: str


class ResearchResponse(BaseModel):
    job_id: str
    status: str
    report: str = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize MCP connections and close them during application shutdown."""
    global mcp_manager
    try:
        logger.info("Initializing MCP servers...")
        filesystem_root = os.getenv("FILESYSTEM_MCP_ROOT", "/tmp/workspaces")
        github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")

        mcp_manager = MCPClientManager(
            filesystem_root=filesystem_root,
            github_token=github_token,
        )

        await mcp_manager.connect()
        set_mcp_manager(mcp_manager)
        logger.info("✓ MCP servers initialized")
    except Exception as e:
        logger.error(f"MCP initialization failed: {e}")
        logger.warning("Service will run with limited capabilities")

    try:
        yield
    finally:
        if mcp_manager:
            await mcp_manager.close()
            logger.info("✓ MCP connections closed")


app = FastAPI(title="Codebase Analysis Service", lifespan=lifespan)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "Codebase Analysis Service is running"}


@app.post("/api/v1/research")
def create_research_job(request: ResearchRequest) -> dict[str, str]:
    """
    Clone a repository and submit a new research job.
    The future background worker will consume the retained workspace.
    """
    job_id = str(uuid4())
    try:
        clone_repository(request.repo_path, job_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to clone repository for job %s: %s", job_id, e)
        raise HTTPException(status_code=400, detail="Unable to clone repository") from e

    logger.info(f"Created research job {job_id}: {request.query}")

    return {
        "job_id": job_id,
        "status": "queued",
    }


@app.post("/api/v1/research-sync")
def research_sync(request: ResearchRequest) -> ResearchResponse:
    """
    Synchronous research endpoint.
    Executes full analysis and returns final report immediately.
    (In production, use async endpoint for long-running tasks)
    """
    job_id = str(uuid4())
    logger.info(f"Running synchronous research {job_id}: {request.query}")

    workspace_path = None
    try:
        workspace_path = clone_repository(request.repo_path, job_id)

        # Build and execute graph
        graph = build_codebase_research_graph()
        initial_state: ResearchState = {
            "repo_path": workspace_path,
            "query": request.query,
            "subtasks": [],
            "research_results": [],
            "final_report": "",
            "error_status": "",
        }

        result = graph.invoke(initial_state)
        final_report = result.get("final_report", "")

        return ResearchResponse(
            job_id=job_id,
            status="completed",
            report=final_report,
        )

    except Exception as e:
        logger.error(f"Research job {job_id} failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Research failed: {type(e).__name__}: {str(e)}",
        )
    finally:
        if workspace_path and os.getenv("WORKSPACE_CLEANUP", "true").lower() == "true":
            remove_workspace(workspace_path)