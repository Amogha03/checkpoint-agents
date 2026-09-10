# Claude Code Notes

This document records how Claude Code was used during development of the Codebase Analysis project.

## Parts Built With Claude Code

The following project areas were implemented or substantially developed with Claude Code:

- **LangGraph agent orchestration:** Designed and implemented the workflow node by node in `app/agents/graph.py`, `app/agents/state.py`, and `app/agents/nodes.py`. This includes the security-focused Planner, MCP-backed Researcher, Synthesizer, structured state, conditional routing, findings accumulation, and cited Markdown report generation.
- **FastAPI service layer:** Developed `app/main.py` with request validation, asynchronous job execution, MCP startup and shutdown lifecycle handling, health checks, safe exception handlers, request observability, and research endpoints.
- **In-memory job management:** Implemented `app/job_store.py` to track queued, running, completed, and failed jobs by UUID with thread-safe access and report storage.
- **Repository ingestion and cleanup:** Implemented the isolated clone lifecycle in `app/ingestion.py`, including per-job workspace paths, repository cloning, and cleanup after processing.
- **MCP integration:** Developed the Filesystem and GitHub MCP client lifecycle and LangChain tool wrappers in `app/tools/mcp_client.py`, including stdio transport management, path resolution, tool errors, and grounded file citations.
- **Logging and debugging:** Added structured service logging and request observability in `app/main.py`, including route, response status, duration, job ID, and safe error context. Added defensive logging around planner, researcher, synthesizer, MCP, cloning, and job execution failures to make asynchronous research runs easier to diagnose without exposing request bodies, credentials, or internal stack traces to clients.

## Prompting Workflow

The prompting workflow was iterative and implementation-focused:

1. **Describe the requirement precisely:** I started with a concrete engineering goal, such as hardening the FastAPI service, implementing the agent orchestration, improving security-only behavior, or correcting report citations. Prompts usually included the expected behavior, constraints, and acceptance criteria.
2. **Provide repository context:** I identified the relevant files and modules, such as `app/main.py`, `app/agents/`, `app/tools/`, and the evaluation files. Prompts referenced the existing code and explained which interfaces, endpoints, or ownership boundaries needed to remain compatible.
3. **Request focused implementation:** Claude Code was asked to make small, targeted changes rather than redesigning unrelated parts of the system. For larger features, the work was broken down node by node or module by module, followed by a review of the resulting implementation.
4. **Validate the behavior:** After each meaningful change, I used focused checks such as Python compilation, diagnostics, mocked planner tests, API smoke tests, MCP verification, and the golden evaluation suite. I also inspected generated reports and LangSmith traces to verify the actual runtime behavior.
5. **Iterate on incorrect results:** When the output did not match the requirement, I provided the observed report or error and asked for a targeted correction. This included refining prompts, fixing citation formatting and path handling, removing irrelevant citations, and adding non-security regression cases. When a session continued making unsupported deductions, I started a fresh session with the corrected problem framing.

## Corrections Required

One issue that required correction was an incorrect diagnosis of the repository-analysis output:

- **Issue:** Claude Code inferred that the request's `local_path: "."` was being replaced by a different repository path. The path was correct; the actual problem was that the generated output was inaccurate.
  **Correction:** I clarified that the path was not the issue and that the output quality needed attention. Claude Code continued making unsupported deductions and hallucinating instead of correcting the analysis, so I started a fresh session to resolve the error.


## Meaningful Prompt Example

**Prompt:**

```text
You are an expert AI Engineer. We are hardening the production FastAPI service layer for our Codebase Analysis system. 

Your task is to update @main.py and our error/logging utilities to satisfy strict validation, safety, and observability requirements.

Objectives for Request Validation, Error Handling & Logging

1. Request Validation & Status Codes
- Add Pydantic field validators (e.g., using `field_validator` or `constr`) on `ResearchRequest` to ensure that `repo_path` (or `repo_url`) and `query` are present and not empty or whitespace-only. 
- Automatically reject empty or malformed questions/repositories with HTTP `400 Bad Request`.
- Ensure `GET /jobs/{job_id}` explicitly checks the job registry and returns HTTP `404 Not Found` if the `job_id` does not exist.

2. Structured Error Handling
- Implement global FastAPI exception handlers for `HTTPException` and unhandled general `Exception`s.
- Never leak raw Python stack traces or internal traceback details to API clients.
- Return a standardized, structured JSON error response format:
  ```json
  {
    "error": "Bad Request | Not Found | Internal Server Error",
    "detail": "Descriptive, safe message explaining the failure",
    "status_code": 400
  }
```

**Resulting code or contribution:**

The prompt produced a hardened FastAPI service layer in `app/main.py`. The implementation added Pydantic validation for repository URLs and research queries, standardized HTTP error responses, protected clients from internal exception details, and added explicit `404 Not Found` handling for unknown job IDs. It also added request observability that records route, status, duration, job ID, and safe error information without logging request bodies or secrets.

**Why it was meaningful:**

This was meaningful because it converted broad production-hardening requirements into concrete API behavior and operational safeguards. Invalid requests fail early with predictable status codes, clients receive a consistent response format, internal implementation details remain private, and logs provide enough information to diagnose requests without exposing sensitive data.
