"""
Agent node implementations for the codebase analysis workflow.
Each node (Planner, Researcher, Synthesizer) performs a specific stage of the pipeline.
Phase 3: Uses real MCP tools via LLM tool-calling for dynamic research.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from langchain_core.messages import ToolMessage
from app.llm import get_llm, get_llm_with_structured_output
from app.agents.state import ResearchState, SubTaskList
from app.tools import get_mcp_manager, get_mcp_tools

logger = logging.getLogger(__name__)


DISCOVERY_PATTERNS = (
    "**/*auth*",
    "**/*login*",
    "**/*token*",
    "**/*session*",
    "**/*security*",
    "**/pyproject.toml",
    "**/requirements*.txt",
    "**/.env*",
)


async def _discover_repository(repo_path: str, mcp_manager: Any) -> str:
    """Build a grounded file inventory before asking the LLM for conclusions."""
    discovered: list[str] = []
    for pattern in DISCOVERY_PATTERNS:
        result = await mcp_manager.call_tool(
            "filesystem",
            "search_files",
            {"path": repo_path, "pattern": pattern},
        )
        if result and not result.startswith("Error "):
            discovered.append(f"Pattern {pattern}:\n{result}")
    return "\n\n".join(discovered) or "No matching files were returned by MCP."


def _line_citation(filepath: str, content: str) -> dict[str, str]:
    """Create a citation whose line range is derived from returned content."""
    line_count = max(1, len(content.splitlines()))
    return {
        "file": filepath,
        "lines_read": f"1-{line_count}",
        "snippet_preview": content[:4000],
    }


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
3. Decompose it into 2-5 concrete subtasks.
4. Each subtask should specify:
   - A unique task_id (e.g., "task_1", "task_2")
   - A clear description of what to research
    - A broad concept or glob pattern to focus on (e.g., "authentication", "**/*auth*", "JWT validation")

Never assume that directories such as auth/, middleware/, or api/auth/ exist. The researcher will verify paths against the cloned repository.

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


async def researcher_node(state: ResearchState) -> dict[str, Any]:
    """
    Researcher Agent: Uses LLM with tool-calling to research subtasks via MCP.

    Inputs:
        state["repo_path"]: Local filesystem path to cloned repository.
        state["subtasks"]: List of research subtasks from Planner.

    Outputs:
        Returns dict with "research_results" key (list of finding dicts).
        Uses operator.add reducer in LangGraph to append to state["research_results"].

    Behavior (Phase 3 - LLM-driven):
        - For each subtask, invokes LLM with MCP tools bound.
        - LLM decides which files to search/read based on subtask description.
        - All MCP tool calls wrapped in try/except; errors logged gracefully.
        - If MCP server down or tool fails, returns error string, LLM continues.
        - Appends structured findings with task_id and citations.

    Error Handling:
        - Tool execution errors are caught and returned as strings to LLM.
        - LLM sees errors and adapts (tries different patterns, etc).
        - Node never raises exceptions; always returns findings dict.
    """
    repo_path = state["repo_path"]
    subtasks = state["subtasks"]

    logger.info(f"Researcher: Processing {len(subtasks)} subtask(s) from repo: {repo_path}")

    findings_list = []
    mcp_tools = get_mcp_tools()
    mcp_manager = get_mcp_manager()
    if not mcp_manager:
        return {
            "research_results": [
                {
                    "task_id": "mcp_unavailable",
                    "description": "MCP manager initialization",
                    "findings": [],
                    "file_citations": [],
                    "errors": ["MCP manager is not initialized"],
                }
            ]
        }
    try:
        repository_inventory = await _discover_repository(repo_path, mcp_manager)
    except Exception as exc:
        repository_inventory = f"Repository discovery failed: {type(exc).__name__}: {exc}"
        logger.warning("Researcher: %s", repository_inventory)
    llm_with_tools = get_llm().bind_tools(mcp_tools)

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
            # Invoke LLM with tool-calling to research this subtask
            research_prompt = f"""You are a code researcher examining a codebase to answer a specific research question.

Repository Path: {repo_path}
Task ID: {task_id}
Task Description: {description}
Focus On: {target_concept}

Your job:
1. Start from the verified repository inventory below; do not invent paths.
2. Use the mcp_search_files tool with glob patterns to find additional relevant files.
3. Use the mcp_read_file tool to examine files returned by MCP.
4. Analyze only content returned by MCP and report what you discovered.

Verified repository inventory:
{repository_inventory}

Provide clear, concise findings with citations only to files actually returned and read by MCP.
If no relevant implementation exists, say "No evidence found in the files searched" and list the verified search patterns. Do not claim that the repository has no vulnerability solely because a guessed directory is absent."""

            messages = [{"role": "user", "content": research_prompt}]
            for _ in range(6):
                response = await llm_with_tools.ainvoke(messages)
                messages.append(response)
                tool_calls = getattr(response, "tool_calls", []) or []
                if not tool_calls:
                    response_text = response.content
                    if response_text:
                        task_findings["findings"].append(response_text)
                    break

                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_input = tool_call.get("args", {})
                    logger.debug(f"LLM called tool: {tool_name}({tool_input})")
                    try:
                        if tool_name == "mcp_search_files":
                            result = await mcp_manager.call_tool(
                                "filesystem",
                                "search_files",
                                {
                                    "path": tool_input.get("repo_path", repo_path),
                                    "pattern": tool_input.get("pattern", "*"),
                                },
                            )
                        elif tool_name == "mcp_read_file":
                            filepath = tool_input.get("filepath", "")
                            arguments = {"path": filepath}
                            if tool_input.get("start_line", 1) > 1:
                                arguments["startLine"] = tool_input["start_line"]
                            if tool_input.get("end_line"):
                                arguments["endLine"] = tool_input["end_line"]
                            result = await mcp_manager.call_tool(
                                "filesystem", "read_file", arguments
                            )
                            if result and not result.startswith("Error "):
                                task_findings["file_citations"].append(
                                    {
                                        "file": filepath,
                                        **_line_citation(filepath, result),
                                    }
                                )
                            else:
                                task_findings["errors"].append(result)
                        else:
                            result = f"Error: unsupported tool {tool_name}"
                        messages.append(
                            ToolMessage(content=result, tool_call_id=tool_call["id"])
                        )
                    except Exception as e:
                        error_msg = f"Tool {tool_name} error: {type(e).__name__}: {str(e)}"
                        task_findings["errors"].append(error_msg)
                        messages.append(
                            ToolMessage(content=error_msg, tool_call_id=tool_call["id"])
                        )
            else:
                task_findings["errors"].append("Tool-call limit reached")

        except Exception as e:
            error_msg = f"Task {task_id} research error: {type(e).__name__}: {str(e)}"
            task_findings["errors"].append(error_msg)
            logger.error(f"Researcher: {error_msg}")

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

    synthesis_prompt = f"""You are the lead security analyst. Produce a new report from the evidence below; do not merely repeat the researcher notes.

**Original Query:**
{query}

**Evidence Dossier:**
{findings_text}

**Synthesis workflow:**
1. Identify what the repository actually does from the returned code, then compare that architecture with the query.
2. Consolidate overlapping task results into meaningful security findings. Do not produce one shallow section per task.
3. Distinguish confirmed vulnerabilities, security-relevant observations, and absence of an applicable feature.
4. For each confirmed or materially relevant observation, explain impact and why the code supports it.
5. Prioritize findings as Critical, High, Medium, Low, or Informational, and state confidence based on the evidence read.
6. Discuss credential handling, access control, sessions, dependencies, and input/prompt handling only when the dossier contains relevant evidence.
7. Cite only files and line ranges in the Sources allowlist. Never invent filenames, line ranges, snippets, vulnerabilities, or repository structure.
8. If a claim has no supporting source, write "Not verified from the files read" instead of presenting it as a finding.
9. If no relevant implementation exists, say "No evidence found in the files searched" and explain the verified search scope. Do not claim the repository is vulnerability-free.
10. End with concrete remediation recommendations only for confirmed or materially relevant observations.

**Required report structure:**
# Security & Access Control Analysis Report
## Query
## Executive Summary
## Repository Scope
## Key Findings & Codebase Localization
### [severity] Finding title
- Finding
- Impact
- Evidence
- Recommendation
## Citations
## Limitations

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

## Limitations
The report could not be synthesized from the collected evidence. Review the service logs for the internal failure details.
"""

    return {**state, "final_report": final_report}
