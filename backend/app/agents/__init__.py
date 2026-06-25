"""LangGraph workflow placeholders for agent orchestration."""

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class AgentState(TypedDict):
    message: str


def build_demo_graph():
    graph = StateGraph(AgentState)

    def echo(state: AgentState) -> AgentState:
        return {"message": state["message"]}

    graph.add_node("echo", echo)
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph.compile()


# Export the Multi-Agent proposal generation workflow
from app.agents.workflow import ProposalState, proposal_graph

# Export the Invoice Ops workflow
from app.agents.ops_workflow import OpsState, invoice_ops_graph

