# checkpoint-agents

Business Problem:
Analysts at a mid-sized professional services firm currently spend roughly 4 hours per day performing manual, early-stage research. For technical due diligence and security audits, this involves manually clicking through large codebase repositories, tracing execution flows, and reading raw code to answer specific client questions. This is an expensive, slow, and unscalable use of high-tier talent.

Technical Objective:
Build an automated, internal "Clone & Scan" Codebase Analysis Service. The system must take a repository URL and a research query, securely clone the repository to an ephemeral local workspace, and deploy a multi-agent LLM workflow (managed via LangGraph). These agents must use a local Filesystem MCP (Model Context Protocol) server to search and read the local codebase efficiently. The output must be a highly accurate, Markdown-formatted report backed by exact file path and line-number citations. The entire pipeline must be traceable in LangSmith and evaluatable against a golden task set to ensure accuracy and prevent hallucinations.

In this model, the system first pulls the repository down to an ephemeral (temporary) local disk. Once the code is local, your multi-agent system uses a Filesystem MCP Server as its primary tool to instantly search, read, and analyze the codebase without worrying about GitHub API rate limits or network latency.


# Architecture
                                ┌──────────────────────────────────────────┐
                                │               USER REQUEST               │
                                │  POST /api/v1/research                   │
                                │  { "repo": "https://github/org/repo",    │
                                │    "query": "Find auth vulnerabilities"} │
                                └────────────────────┬─────────────────────┘
                                                     │
 ┌───────────────────────────────────────────────────▼───────────────────────────────────────────────────┐
 │                                       FASTAPI SERVICE LAYER                                           │
 │                                                                                                       │
 │  1. Ingestion Worker:                                                                                 │
 │     Executes `git clone https://... /tmp/workspaces/job_123`                                          │
 │                                                                                                       │
 │  2. Context Setup:                                                                                    │
 │     Initializes LangSmith tracing & passes local path `/tmp/workspaces/job_123` to Agents             │
 └───────────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                                     │ (Traced via LangSmith)
                                                     ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   AGENT ORCHESTRATION (LANGGRAPH)                                     │
 │                                                                                                       │
 │                       ┌──────────────────────────────────────────────┐                                │
 │                       │             LEAD PLANNER AGENT               │                                │
 │                       │ Breaks query into sub-tasks (e.g., "Find     │                                │
 │                       │ middleware", "Check JWT validation")         │                                │
 │                       └──────┬───────────────────────────────┬───────┘                                │
 │                              │                               │                                        │
 │           ┌──────────────────▼──────────────┐  ┌─────────────▼──────────────────┐                     │
 │           │    ARCHITECTURE SUB-AGENT       │  │      SECURITY SUB-AGENT        │                     │
 │           │ Focus: Routing, Dependencies,   │  │ Focus: Auth flows, Data        │                     │
 │           │ File Structures                 │  │ validation, Secrets            │                     │
 │           └─────────┬───────────────────────┘  └──────────────┬─────────────────┘                     │
 │                     │                                         │                                       │
 │                     └───────────────────┬─────────────────────┘                                       │
 │                                         │ JSON-RPC Tool Calls                                         │
 │                                         ▼                                                             │
 │  ===================================================================================================  │
 │  ||                              FILESYSTEM MCP SERVER (Local)                                    ||  │
 │  ||  Tools exposed to agents:                                                                     ||  │
 │  ||  - list_directory(path)        - read_file(path, start_line, end_line)                        ||  │
 │  ||  - search_files(regex_pattern) - get_file_info(path)                                          ||  │
 │  =======================================▲===========================================================  │
 │                                         │ (Instant local disk access)                                 │
 │                                         ▼                                                             │
 │                       ┌──────────────────────────────────────────────┐                                │
 │                       │       EPHEMERAL LOCAL DISK WORKSPACE         │                                │
 │                       │  /tmp/workspaces/job_123/ (Cloned Repo Code) │                                │
 │                       └──────────────────────────────────────────────┘                                │
 │                                                                                                       │
 │                                         │ (Sub-agents return findings)                                │
 │                                         ▼                                                             │
 │                       ┌──────────────────────────────────────────────┐                                │
 │                       │             SYNTHESIZER AGENT                │                                │
 │                       │ Compiles findings, verifies line numbers,    │                                │
 │                       │ formats Markdown report with exact citations │                                │
 │                       └──────────────────────────────────────────────┘                                │
 └─────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │    FINAL RESPONSE    │
                                │ (Markdown + Cleanup  │
                                │  /tmp/workspaces/)   │
                                └──────────────────────┘

