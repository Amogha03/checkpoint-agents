"""
LangGraph workflow orchestration for the codebase analysis system.

This module constructs the complete state graph with three agents:
1. Planner: Decomposes query into subtasks
2. Researcher: Gathers findings from codebase
3. Synthesizer: Generates final report

The graph includes conditional routing after the Planner to handle invalid queries.
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import planner_node, researcher_node, synthesizer_node
from app.agents.state import ResearchState

logger = logging.getLogger(__name__)


# ============================================================================
# CONDITIONAL ROUTING FUNCTION
# ============================================================================


def route_after_planner(state: ResearchState) -> str:
    """
    Conditional router executed after the Planner node.

    Routing Rule:
        If state["subtasks"] is empty (length == 0):
            → Route to "synthesizer" (invalid/unrelated query handling)
        Otherwise:
            → Route to "researcher" (proceed with research)

    Rationale:
        An empty subtask list from the Planner indicates that:
        - The user query is unrelated to codebase analysis (e.g., "Tell me a joke")
        - The query is too vague to decompose (e.g., "Analyze the code")
        In these cases, we skip research and go straight to the Synthesizer,
        which generates a helpful message explaining the issue.

        A non-empty subtask list means the query is valid and actionable,
        so we proceed to the Researcher to gather findings.

    Args:
        state: Current ResearchState from the Planner.

    Returns:
        str: Node name ("researcher" or "synthesizer")
    """
    subtasks = state.get("subtasks", [])
    num_subtasks = len(subtasks)

    logger.info(
        f"Router: Planner generated {num_subtasks} subtask(s). Routing to "
        f"{'synthesizer' if num_subtasks == 0 else 'researcher'}"
    )

    if num_subtasks == 0:
        return "synthesizer"
    else:
        return "researcher"


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================


def build_codebase_research_graph():
    """
    Constructs and returns the compiled LangGraph workflow.

    Graph Structure:
        planner (entry point)
           ↓
        [conditional routing]
           ├─ (if subtasks == 0) → synthesizer → END
           └─ (if subtasks > 0) → researcher → synthesizer → END

    Nodes:
        - "planner": Decomposes query into subtasks
        - "researcher": Gathers findings for each subtask
        - "synthesizer": Generates final Markdown report

    Edges:
        - planner → [router] → researcher OR synthesizer
        - researcher → synthesizer
        - synthesizer → END

    Returns:
        Compiled StateGraph ready for invocation with .invoke() or .stream()
    """
    graph = StateGraph(ResearchState)

    # Add the three agent nodes.
    graph.add_node("planner", planner_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("synthesizer", synthesizer_node)

    # Set entry point.
    graph.add_edge(START, "planner")

    # Add conditional edge from Planner.
    # This uses the route_after_planner function to decide the next node.
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "researcher": "researcher",
            "synthesizer": "synthesizer",
        },
    )

    # Add standard edges.
    graph.add_edge("researcher", "synthesizer")
    graph.add_edge("synthesizer", END)

    # Compile the graph.
    compiled_graph = graph.compile()

    logger.info("Codebase research graph compiled successfully")
    return compiled_graph


# ============================================================================
# EXPORTED GRAPH
# ============================================================================

codebase_research_graph = build_codebase_research_graph()
print(codebase_research_graph)