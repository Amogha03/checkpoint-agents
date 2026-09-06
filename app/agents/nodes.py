"""
Agent node implementations for the codebase analysis workflow.
Each node (Planner, Researcher, Synthesizer) performs a specific stage of the pipeline.
"""

import logging
import re
from typing import Any

from app.llm import get_llm, get_llm_with_structured_output
from app.agents.state import ResearchState, SubTaskList

logger = logging.getLogger(__name__)


# ============================================================================
# MOCK TOOLS (Phase 2 placeholder; real MCP integration in Phase 3)
# ============================================================================


def mock_mcp_read_file(filepath: str, start_line: int = 1, end_line: int = None) -> str:
    """
    Mock tool simulating MCP read_file capability.
    In Phase 3, this will be replaced by real MCP server calls.

    Args:
        filepath: Relative or absolute path to file in the cloned repo.
        start_line: Starting line number (1-indexed).
        end_line: Ending line number (1-indexed). If None, reads to EOF.

    Returns:
        File contents or error message if file not found.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            start_idx = max(0, start_line - 1)
            end_idx = len(lines) if end_line is None else min(len(lines), end_line)
            return "".join(lines[start_idx:end_idx])
    except FileNotFoundError:
        return f"[ERROR] File not found: {filepath}"
    except Exception as e:
        return f"[ERROR] Failed to read {filepath}: {type(e).__name__}: {str(e)}"


def mock_mcp_search_files(repo_path: str, pattern: str) -> list[str]:
    """
    Mock tool simulating MCP search_files capability.
    Returns files matching a regex pattern or simple substring.

    Args:
        repo_path: Root directory of cloned repository.
        pattern: Regex pattern or simple substring to match filenames.

    Returns:
        List of matching file paths (relative to repo_path).
    """
    import os

    try:
        matches = []
        for root, dirs, files in os.walk(repo_path):
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, repo_path)
                try:
                    if re.search(pattern, rel_path):
                        matches.append(rel_path)
                except re.error:
                    if pattern in rel_path:
                        matches.append(rel_path)
        return matches[:20]
    except Exception as e:
        logger.warning(f"Mock search error: {e}")
        return []


# ============================================================================
# PLANNER NODE
# ============================================================================


def planner_node(state: ResearchState) -> ResearchState:
    """
    Planner Agent: Decomposes the user query into discrete research subtasks.

    Inputs:
        state["query"]: The user's research question.

    Outputs:
        state["subtasks"]: List of SubTask objects structured as dicts.
        state["error_status"]: Set if query is invalid/unrelated.

    Behavior:
        - Uses configured LLM (OpenAI or Anthropic) with structured output (SubTaskList).
        - If the query is completely unrelated to codebase analysis or too vague,
          the LLM returns an empty list of tasks.
        - This triggers conditional routing to the Synthesizer (empty task handling).

    Routing Logic (downstream):
        If len(subtasks) == 0: route to Synthesizer directly.
        Otherwise: route to Researcher.
    """
    query = state["query"]
    logger.info(f"Planner: Processing query: {query}")

    prompt = f"""You are a query decomposition expert for codebase analysis.

Your task is to break down the following research query into concrete, actionable subtasks that can be performed by examining a codebase.

Query: {query}

Instructions:
1. If the query is completely unrelated to codebase analysis (e.g., "Tell me a joke", "What is the weather?"), return an empty list.
2. If the query is too vague to decompose into specific research tasks, return an empty list.
3. If the query is valid and related to codebase analysis, decompose it into 2-5 concrete subtasks.
4. Each subtask should specify:
   - A unique task_id (e.g., "task_1", "task_2")
   - A clear description of what to research
   - A target_concept or file pattern to focus on (e.g., "auth.py", "middleware/*", "JWT validation")

Return a JSON structure with these tasks. If invalid/too vague, return an empty tasks list."""

    try:
        llm_with_structured = get_llm_with_structured_output(SubTaskList)
        result: SubTaskList = llm_with_structured.invoke(prompt)
        subtasks = [
            {
                "task_id": task.task_id,
                "description": task.description,
                "target_concept": task.target_concept,
            }
            for task in result.tasks
        ]
        logger.info(f"Planner: Generated {len(subtasks)} subtask(s)")
        return {
            **state,
            "subtasks": subtasks,
            "error_status": "" if subtasks else "query_invalid",
        }
    except Exception as e:
        logger.error(f"Planner: Error during decomposition: {e}")
        return {
            **state,
            "subtasks": [],
            "error_status": f"planner_error: {str(e)}",
        }


# ============================================================================
# RESEARCHER NODE
# ============================================================================


def researcher_node(state: ResearchState) -> dict[str, Any]:
    """
    Researcher Agent: Gathers findings for each subtask using mock MCP tools.

    Inputs:
        state["repo_path"]: Local filesystem path to cloned repository.
        state["subtasks"]: List of research subtasks from Planner.

    Outputs:
        Returns dict with "research_results" key (list of finding dicts).
        Uses operator.add reducer in LangGraph to append to state["research_results"].

    Behavior:
        - Iterates through each subtask.
        - Attempts to search for relevant files and read content.
        - Wraps all tool calls in try/except to gracefully handle errors.
        - If a tool call fails (file not found, MCP error), logs the error and continues.
        - Appends structured findings with task_id and file citations.

    Error Handling (Crucial):
        - File not found? Log it, continue with next file.
        - MCP server unavailable? Log it, continue.
        - No findings for a task? Still append a result dict noting the issue.
        - Never crash or raise exceptions; always return a dict.
    """
    repo_path = state["repo_path"]
    subtasks = state["subtasks"]

    logger.info(f"Researcher: Processing {len(subtasks)} subtask(s) from repo: {repo_path}")

    findings_list = []

    for subtask in subtasks:
        task_id = subtask.get("task_id", "unknown")
        description = subtask.get("description", "")
        target_concept = subtask.get("target_concept", "")

        logger.info(
            f"Researcher: Researching task {task_id}: {description} (target: {target_concept})"
        )

        task_findings = {
            "task_id": task_id,
            "description": description,
            "findings": [],
            "file_citations": [],
            "errors": [],
        }

        try:
            # Step 1: Search for files matching the target concept.
            search_pattern = target_concept.replace("*", ".*").replace("/", "/")
            search_results = mock_mcp_search_files(repo_path, search_pattern)

            if not search_results:
                task_findings["errors"].append(
                    f"No files matched pattern: {target_concept}"
                )
                logger.warning(
                    f"Researcher: No files found for task {task_id}, pattern: {target_concept}"
                )
            else:
                logger.info(f"Researcher: Found {len(search_results)} file(s) for task {task_id}")

                # Step 2: For each matching file, attempt to read and extract content.
                for file_rel_path in search_results[:3]:
                    file_full_path = f"{repo_path}/{file_rel_path}"

                    try:
                        content = mock_mcp_read_file(file_full_path)

                        if content.startswith("[ERROR]"):
                            task_findings["errors"].append(content)
                            logger.warning(f"Researcher: {content}")
                        else:
                            lines = content.split("\n")
                            summary = " ".join(lines[:3])
                            task_findings["file_citations"].append(
                                {
                                    "file": file_rel_path,
                                    "lines_read": len(lines),
                                    "snippet_preview": summary[:150],
                                }
                            )
                            task_findings["findings"].append(
                                f"Examined {file_rel_path}: {summary[:100]}..."
                            )

                    except Exception as e:
                        error_msg = f"Failed to read {file_rel_path}: {type(e).__name__}: {str(e)}"
                        task_findings["errors"].append(error_msg)
                        logger.warning(f"Researcher: {error_msg}")

        except Exception as e:
            task_findings["errors"].append(
                f"Task {task_id} processing error: {type(e).__name__}: {str(e)}"
            )
            logger.error(f"Researcher: Unhandled exception in task {task_id}: {e}")

        findings_list.append(task_findings)

    logger.info(f"Researcher: Completed research. Generated {len(findings_list)} result(s)")

    return {"research_results": findings_list}


# ============================================================================
# SYNTHESIZER NODE
# ============================================================================


def synthesizer_node(state: ResearchState) -> ResearchState:
    """
    Synthesizer Agent: Generates final Markdown report from research findings.

    Inputs:
        state["query"]: Original user research question.
        state["research_results"]: Accumulated findings from researchers.
        state["subtasks"]: Original subtasks (for context).
        state["error_status"]: Any error flags from upstream nodes.

    Outputs:
        state["final_report"]: Markdown-formatted report with exact citations.

    Behavior:
        - If error_status is set (e.g., invalid query), generates a helpful message.
        - If research_results is empty, generates a summary explaining lack of findings.
        - Otherwise, synthesizes findings into a structured Markdown report.
        - IMPORTANT: Generates citations pointing to specific source identifiers
          (e.g., "app/main.py (Lines 12-20)") based on file_citations, not free text.
        - Uses an LLM to format, organize, and prioritize findings.

    Report Structure (Generated):
        # Research Report
        ## Query
        [Original user query]

        ## Summary
        [1-2 sentence overview]

        ## Findings
        ### Finding 1
        [Detailed finding with citation to source]
        ...

        ## Limitations
        [Note any files not found, errors encountered, etc.]
    """
    query = state["query"]
    research_results = state.get("research_results", [])
    error_status = state.get("error_status", "")
    subtasks = state.get("subtasks", [])

    logger.info(f"Synthesizer: Generating report for query: {query}")

    # Handle error cases early.
    if error_status and "invalid" in error_status.lower():
        final_report = f"""# Research Report

## Query
{query}

## Status
⚠️ **Invalid Input**: The provided query is not related to codebase analysis or is too vague to decompose into specific research tasks.

## Recommendation
Please rephrase your query to focus on:
- Specific code patterns or vulnerabilities (e.g., "Find JWT validation logic")
- Architecture or design patterns (e.g., "Identify dependency injection usage")
- Security concerns (e.g., "Find hardcoded secrets")
- Code organization (e.g., "Map the authentication module")
"""
        logger.info("Synthesizer: Returned error report for invalid query")
        return {**state, "final_report": final_report}

    if not research_results or (len(research_results) == 1 and not research_results[0].get("findings")):
        final_report = f"""# Research Report

## Query
{query}

## Status
⚠️ **No Findings**: The research process did not locate relevant code matching the query.

## Possible Reasons
- The repository does not contain the requested functionality.
- The codebase structure differs from expected patterns.
- The query targets very specific or deeply nested code.

## Recommendations
- Review the repository structure manually.
- Rephrase your query with different keywords or file patterns.
- Provide more context about the codebase organization.
"""
        logger.info("Synthesizer: Returned empty report (no findings)")
        return {**state, "final_report": final_report}

    llm = get_llm()

    findings_text = ""
    for result in research_results:
        task_id = result.get("task_id", "unknown")
        description = result.get("description", "")
        findings = result.get("findings", [])
        citations = result.get("file_citations", [])
        errors = result.get("errors", [])

        findings_text += f"\n### Task: {task_id} - {description}\n"
        if findings:
            findings_text += f"**Findings:**\n"
            for finding in findings:
                findings_text += f"- {finding}\n"
        if citations:
            findings_text += f"**Sources:**\n"
            for citation in citations:
                file_path = citation.get("file", "unknown")
                lines_read = citation.get("lines_read", "?")
                snippet = citation.get("snippet_preview", "")
                findings_text += f"  - {file_path} ({lines_read} lines): {snippet}\n"
        if errors:
            findings_text += f"**Errors/Warnings:**\n"
            for error in errors:
                findings_text += f"  - {error}\n"

    synthesis_prompt = f"""You are a senior code analyst. Synthesize the following research findings into a professional, well-organized Markdown report.

**Original Query:**
{query}

**Raw Research Findings:**
{findings_text}

**Instructions:**
1. Create a structured Markdown report with sections: Query, Summary, Findings, Limitations.
2. For each finding, include EXACT citations like "src/auth.py (Lines 42-55)" based on the file paths and line counts provided.
3. Do NOT invent sources; only cite files and line ranges explicitly mentioned in the raw findings.
4. If a finding spans multiple files, list all relevant sources.
5. Use clear headers and bullet points for readability.
6. Include a Limitations section noting any files not found or errors encountered.
7. Ensure all claims are traceable back to specific code locations.

Generate the final report now:"""

    try:
        response = llm.invoke(synthesis_prompt)
        final_report = response.content
        logger.info("Synthesizer: Report generated successfully")
    except Exception as e:
        logger.error(f"Synthesizer: Error during synthesis: {e}")
        final_report = f"""# Research Report

## Query
{query}

## Status
⚠️ **Synthesis Error**: Failed to synthesize findings into a report.

## Raw Findings
{findings_text}

## Error Details
{type(e).__name__}: {str(e)}
"""

    return {**state, "final_report": final_report}
