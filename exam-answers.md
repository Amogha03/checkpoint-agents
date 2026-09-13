# Exam Answers

## Q1 (2 pts)

**Question:** In one paragraph, define the difference between an LLM chain and an agent. Use the system you just built as an example. What in your system makes it an agent rather than a chain?

**Answer:**

An LLM chain follows a set sequence of steps, while an agent can decide what to do next based on what it learns along the way.
For example, the Researcher in this project acts like an agent because it chooses which MCP search or file-reading tools to use, looks at the results, and decides whether it needs to keep investigating. That ability to choose and adapt its actions is what makes the system agentic rather than just a fixed LLM chain.


## Q2 (3 pts)

**Question:** Name three concrete failure modes that get worse as you scale an agentic system from a single agent to multiple agents. For each, name the mitigation pattern.

**Answer:**

- **Conflicting or duplicated work:** Multiple agents may investigate the same issue or produce recommendations that disagree. **Mitigation:** Use a supervisor or coordinator to assign distinct tasks, define ownership, and merge results.
- **Errors spreading between agents:** One agent can pass an incorrect assumption to the next agent, which then treats it as fact. **Mitigation:** Require shared evidence, structured handoffs, and verification or reviewer agents before accepting a conclusion.
- **Higher cost and runaway loops:** More agents create more LLM calls, tool calls, and opportunities for agents to keep delegating work without making progress. **Mitigation:** Set explicit budgets, timeouts, maximum iterations, and stop conditions for each task.


## Q3 (4 pts)

**Question:** In LangGraph, what is the difference between a regular edge and a conditional edge, and what is the State object actually doing under the hood? Answer with reference to the `StateGraph` you wrote in your build.

**Answer:**

A regular edge always sends execution to a specific next node. In this system, the  edge from `START` to `planner` and the edge from `researcher` to `synthesizer` are regular edges because those transitions always happen. A conditional edge chooses the next node by evaluating the current state (based on a condition). After the Planner runs, the graph checks whether subtasks were created: a non-security query goes directly to the Synthesizer, while a valid security query goes to the Researcher.

The State object is the shared data passed through all the nodes in the graph. In this build, `ResearchState` carries the repository path, original query, planned subtasks, research results, final report, and error status. Each node reads the fields it needs and returns updates, which LangGraph merges into the state before passing it to the next node. This lets the nodescommunicate through structured data without directly calling one another.


## Q4 (4 pts)

**Question:** Compare the supervisor pattern vs. the hierarchical pattern vs. the swarm pattern for multi-agent orchestration in LangGraph. Give one scenario where each is the right answer.

**Answer:**

The **supervisor pattern** has one supervisor agent decide which specialist agent should act next and combine the results. It is a good fit for a customer-support system where a supervisor routes a request to billing, technical support, or account-security agents.
The **hierarchical pattern** has multiple levels of coordination, such as a manager agent delegating to a domain supervisor that then delegates to smaller workers. It is useful for a large security review where a top-level agent assigns work to authentication, dependency, and data-security supervisors.
The **swarm pattern** allows several peer agents to collaborate more independently by handing work to one another. It is useful for brainstorming or research where several agents can explore different hypotheses in parallel and share findings.
The tradeoff is that supervisors provide more control, heirarchies provide scalability, and swarms provide flexibility but are harder to coordinate and evaluate.


## Q5 (3 pts)

**Question:** You have a text-to-SQL agent backed by LangGraph and MongoDB (as in Unit 2.2’s text-to-query course). A user asks a question that requires data from two collections. Walk through the failure modes you’d expect, and how you would harden the system against each.

**Answer:**

- **The agent chooses the wrong collections or fields:** It may misunderstand the question or the database schema. **Hardening:** Give it an up-to-date schema, require it to explain which collections and fields it selected, and validate those names against an allowlisted schema before execution.
- **The cross-collection query is logically wrong:** It may join on the wrong key, use the wrong relationship, or return duplicate or incomplete records. **Hardening:** Have the agent create an explicit query plan, validate the relationship between the collections, and run a small read-only test or count check before returning the final answer.
- **The generated query is unsafe or too expensive:** The agent could access fields it should not expose, or generate an invalid query that fails at runtime. **Hardening:** Use read-only database credentials, enforce collection and field permissions, add timeouts and result limits, validate the generated query, and return a safe error with a retry.
- **One collection succeeds while the other fails:** A partial result could be presented as if it answered the full question. **Hardening:** Treat the operation as a multi-step workflow with explicit success checks for both queries, preserve errors in state, and only synthesize a final answer when all required evidence is available.


## Q6 (5 pts)

**Question:** You have four agentic projects on your plate: (1) a tightly orchestrated sales-research crew with clearly defined roles, (2) a heavy-document RAG-plus-agent system, (3) a Hugging Face open-source-only deployment for a privacy-sensitive client, (4) a healthcare research agent that must compose Haystack pipelines. For each, pick one of CrewAI, LlamaIndex, smolagents, or Haystack and defend the choice in 2–3 sentences. You may reuse a framework across projects only if you can defend why.

**Answer:**

1. **Sales-research crew: CrewAI.** CrewAI is designed around agents with clear roles, goals, tasks, and collaboration. It fits a tightly orchestrated team where one agent researches prospects, another analyzes competitors, and a final agent prepares the sales brief.
2. **Heavy-document RAG-plus-agent system: LlamaIndex.** LlamaIndex is the best fit because it focuses on ingesting, indexing, retrieving, and querying large document collections. Its data connectors and retrieval abstractions reduce the amount of custom infrastructure needed before adding agent behavior.
3. **Hugging Face open-source-only deployment: smolagents.** smolagents is lightweight and works well with open-source models and Hugging Face tooling, which helps keep the deployment self-hosted and privacy-sensitive. Its simple code-agent approach also reduces framework overhead in an environment where control over the model and runtime matters.
4. **Healthcare research agent: Haystack.** Haystack is the right choice because the requirement explicitly involves composing Haystack pipelines, and it provides structured components for retrieval, routing, ranking, and generation. Its pipeline structure is also useful in healthcare, where each step can be tested, logged, and governed separately.


## Q7 (4 pts)

**Question:** Explain MCP in one paragraph as if you were explaining it to a senior backend engineer who has never heard of it. Then, in a second paragraph, explain why an AI engineer should care about MCP specifically, what does it solve that bespoke tool plumbing does not?

**Answer:**

The Model Context Protocol, or MCP, is a standard interface for connecting an AI application to external tools and data sources. Instead of hard-coding a different integration for every database, filesystem, API, or service, an MCP server exposes capabilities through a consistent protocol and an MCP client discovers and calls those capabilities.

An AI engineer should care because MCP separates the agent’s reasoning from the implementation of its tools. It provides reusable tool contracts, clearer access boundaries, and easier replacement or deployment of tools than bespoke plumbing, while also making tool calls easier to observe and govern. The tradeoff is additional process and dependency overhead, but it avoids tightly coupling every agent to custom Python wrappers or one vendor’s API.

## Q8 (3 pts)

**Question:** Why is async FastAPI especially relevant for LLM-backed services compared to sync FastAPI? Give a concrete example from your own build where async handling matters or would matter at scale.

**Answer:**

LLM-backed requests spend a lot of time waiting on network operations such as model responses, MCP calls etc. Async FastAPI can let the server handle other requests while one job is waiting, whereas a synchronous handler can tie up a worker for the entire duration of the analysis. In this build, `POST /research` immediately returns HTTP `202` and starts `_execute_research` as an asyncio background task; the graph then uses `ainvoke` for the workflow, while blocking clone and cleanup operations run with `asyncio.to_thread`.

At scale, this allows the API to accept multiple research jobs without keeping an HTTP connection open for every long-running LLM request. The tradeoff is that async code requires careful cancellation, timeout, shared-state, and error handling, especially when the job store and background tasks are involved.


## Q9 (3 pts)

**Question:** Your `/research` endpoint hits an LLM provider that randomly returns 500s approximately 2% of the time. Sketch, in code or pseudocode, the retry, timeout, and circuit-breaker pattern you would apply, and explain what you’d log so a teammate could debug a regression next week.

**Answer:**

I would retry only transient failures such as provider 500s, connection errors, and timeouts. I would use exponential backoff with jitter, a short per-call timeout, and a maximum attempt count so a retry cannot create an agent loop or make p95 latency much worse. A circuit breaker would temporarily stop sending requests after a threshold of consecutive failures, then allow a small number of test requests after a cooldown.

```python
async def call_llm_with_resilience(request, circuit):
    if circuit.is_open():
        raise TemporaryServiceError("LLM circuit is open")

    for attempt in range(1, 4):
        started = monotonic()
        try:
            result = await asyncio.wait_for(llm.ainvoke(request), timeout=20)
            circuit.record_success()
            log_llm_call(attempt, elapsed_ms(started), "success")
            return result
        except (Provider5xx, TimeoutError, ConnectionError) as error:
            circuit.record_failure()
            log_llm_call(attempt, elapsed_ms(started), type(error).__name__)
            if attempt == 3:
                raise
            await asyncio.sleep((2 ** (attempt - 1)) + random_jitter())
```

I would log a correlation ID, job ID, model and provider, graph node, attempt number, error category, HTTP status, timeout duration, backoff duration, circuit state, total elapsed time, token usage, and final outcome. I would not log prompts, responses, API keys, or customer data by default; sensitive content would be redacted or sampled in a controlled debugging environment. These logs, combined with LangSmith traces and p50/p95 latency metrics, would show whether the regression came from the provider, retries, a slow node, or the circuit breaker.


## Q10 (3 pts)

**Question:** Compare Cursor, Claude Code, and GitHub Copilot in terms of where each is the right tool. Give one task per tool where it is clearly the strongest choice, and one task where it is clearly not.

**Answer:**

| Tool | Strongest choice | Clearly not the best choice |
| --- | --- | --- |
| **Cursor** | Exploring and refactoring a large codebase interactively, because its editor can use surrounding files and help make multi-file changes while I review them. | A fully autonomous, multi-step repository task that requires the tool to run independently, make decisions, and continue through several validation steps without constant editor interaction. |
| **Claude Code** | A substantial implementation task such as building the FastAPI and LangGraph workflow, where the agent can inspect the repository, edit several related files, run checks, and iterate on failures. | Quick inline completion while I am typing a small function or repetitive code, where a full agent workflow would add unnecessary overhead. |
| **GitHub Copilot** | Fast inline suggestions, boilerplate generation, and small functions directly in the editor, such as completing a Pydantic model or test case. | A broad architectural redesign or debugging task that requires understanding many files, running experiments, and coordinating several changes. |

The tools overlap, but their strengths are different: Cursor is particularly useful for interactive codebase navigation, Claude Code for autonomous implementation workflows, and GitHub Copilot for fast in-editor assistance. The right choice depends on how much context, autonomy, and iteration the task requires.


## Q11 (3 pts)

**Question:** Open your `CLAUDE_CODE_NOTES.md`. Pick one prompt or workflow you used during this build that worked well, and one that failed. For each, explain in 3–4 sentences why it worked or failed, and what you’d change. Paste the prompts verbatim.

**Answer:**

### Workflow That Worked

The production-hardening prompt worked well because it named the target file, the required API behavior, the safety constraints, and the expected response format. It gave Claude Code concrete acceptance criteria, including validation, status codes, safe exception handling, and structured logging. The resulting work was meaningful because it translated a broad goal into testable changes without asking for an unrelated redesign. I would use the same approach again: provide repository context, define the behavior precisely, and validate the result with focused tests.

**Prompt, verbatim:**

```text
We are hardening the production FastAPI service layer for our Codebase Analysis system. 

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
	{
		"error": "Bad Request | Not Found | Internal Server Error",
		"detail": "Descriptive, safe message explaining the failure",
		"status_code": 400
	}
```

### Workflow That Failed

The failed workflow began with an incorrect diagnosis that `local_path: "."` was being replaced with another repository path. The path was actually correct. the real problem was that the generated analysis was inaccurate and included unsupported deductions. The workflow failed because it kept pursuing the wrong hypothesis instead of checking the observed output and grounding conclusions in evidence. I would change it by first verifying the path with a direct test, comparing the generated report with the source evidence, and starting a fresh session with the corrected problem framing when the model continues halluicnating.

**Failure description:**

> **Issue:** Claude Code inferred that the request's `local_path: "."` was being replaced by a different repository path. The path was correct; the actual problem was that the generated output was inaccurate.
> **Correction:** I clarified that the path was not the issue and that the output quality needed attention. Claude Code continued making unsupported deductions and hallucinating instead of correcting the analysis, so I started a fresh session to resolve the error.


## Q12 (8 pts)

**Question:** Imagine you are 90 days into a new AI engineer role. The team owns a customer-support agent that is in production and unreliable: approximately 12% of conversations end in a state the team cannot explain, latency p95 is 18 seconds, and there is no eval harness. You have one quarter to fix it. Write a one-page plan that covers: (a) what you would instrument first and why, (b) the eval harness you would stand up and how you would seed it, (c) which architectural change you would prioritize first and what you would defer, and (d) one bet you would resist making no matter how loud the pressure to make it.

**Answer:**

### (a) Instrumentation First

I would start with LangSmith tracing to capture each conversation’s inputs and outputs, graph-node transitions, LLM calls, tool calls, latency, retries, errors, and token usage. That would help explain the 12% of conversations ending in unknown states and identify whether the main bottleneck is the model, tools, routing, or repeated agent steps. It would also show which step contributes most to the slow cases causing latency of 18 seconds.

I would connect each trace to an application-level correlation ID and record safe structured logs for the request, final state, failure reason, and user escalation. This would let the team move from “the agent failed” to a specific failure category, such as a timeout, malformed tool call, routing error, or unhandled exception.

### (b) Eval Harness

Next, I would build a versioned eval harness with representative support conversations, expected outcomes, safety cases, escalation cases, and known failure cases sampled from production logs. I would remove or anonymize sensitive customer data before adding examples to the dataset.

Each run would check:

- Task success and correct routing
- Grounded answers and refusal behavior
- Tool-call correctness
- Error rate and unexplained terminal states
- Cost and p50/p95 latency

I would run a small regression suite on every prompt or code change and compare the results with a baseline. A larger suite would run nightly or before releases, with failed examples saved for analysis and added back to the regression set after fixes.

### (c) Architecture Priority and Deferrals

The first architectural change I would prioritize is making the workflow explicit and bounded:

1. Define clear states and terminal outcomes.
2. Add timeouts and maximum tool or agent iterations.
3. Route failures to a safe fallback or human escalation.

This directly targets the unexplained 12% and also prevents runaway work that contributes to the 18-second p95. I would defer a larger multi-agent redesign, model migration, or broad rewrite until the traces and evals show that the current architecture is the actual bottleneck.

| Priority now | Defer until evidence exists |
| --- | --- |
| Tracing and failure classification | Multi-agent redesign |
| Bounded state transitions | Model migration |
| Timeouts and safe escalation | Broad rewrite |
| Versioned regression evals | Premature optimization |

### (d) Bet I Would Resist

One bet I would resist is replacing the system with a more complex multi-agent architecture simply because it sounds more advanced or might improve a demo. Without reliable traces and evaluations, that would add more failure points while making the existing problems harder to diagnose. I would prioritize measurable reliability and latency improvements over adding agents or chasing a higher benchmark score.