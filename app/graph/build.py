from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    classify_node,
    decide_node,
    escalate_node,
    respond_node,
    retrieve_node,
    route_after_retrieve,
)
from app.graph.state import TicketState


def build_graph():
    graph = StateGraph(TicketState)

    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("decide", decide_node)
    graph.add_node("respond", respond_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"decide": "decide", "escalate": "escalate"},
    )
    graph.add_edge("decide", "respond")
    graph.add_edge("respond", END)
    graph.add_edge("escalate", END)

    return graph.compile()


triage_graph = build_graph()
