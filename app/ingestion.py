"""Repository ingestion into temporary local workspaces."""

import logging
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

from git import GitCommandError, Repo

logger = logging.getLogger(__name__)


def clone_repository(repo_url: str, job_id: str) -> str:
    """Clone an HTTP(S) repository into the workspace assigned to a job."""
    parsed_url = urlparse(repo_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("repo_url must be a valid HTTP(S) repository URL")

    workspace_root = Path(os.getenv("WORKSPACE_ROOT", "/tmp/workspaces"))
    workspace_path = workspace_root / job_id
    workspace_root.mkdir(parents=True, exist_ok=True)

    try:
        logger.info("Cloning %s into %s", repo_url, workspace_path)
        Repo.clone_from(repo_url, workspace_path)
    except (GitCommandError, OSError):
        shutil.rmtree(workspace_path, ignore_errors=True)
        raise

    return str(workspace_path)


def remove_workspace(workspace_path: str) -> None:
    """Remove a cloned repository workspace after processing."""
    shutil.rmtree(workspace_path, ignore_errors=True)