from datetime import datetime, timezone

from app.graph.state import TicketState
from app.llm import bedrock_client
from app.tools import rag_tool, sql_tool

ESCALATE_SEVERITY = "high"
ESCALATE_CONFIDENCE_THRESHOLD = 0.6


def _log(state: TicketState, node: str, summary: str) -> list[dict]:
    entry = {
        "node": node,
        "summary": summary,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return [*state["audit_trail"], entry]


def classify_node(state: TicketState) -> dict:
    result = bedrock_client.classify_ticket(state["subject"], state["body"])
    return {
        "category": result["category"],
        "severity": result["severity"],
        "confidence": result["confidence"],
        "audit_trail": _log(
            state,
            "classify",
            f"category={result['category']} severity={result['severity']} "
            f"confidence={result['confidence']:.2f}",
        ),
    }


def retrieve_node(state: TicketState) -> dict:
    kb_snippets = rag_tool.search_kb(f"{state['subject']} {state['body']}")
    customer_context = sql_tool.lookup_customer_context(
        state.get("customer_id"), state.get("order_id")
    )
    return {
        "kb_snippets": kb_snippets,
        "customer_context": customer_context,
        "audit_trail": _log(
            state,
            "retrieve",
            f"kb_hits={len(kb_snippets)} customer_found={customer_context['found']}",
        ),
    }


def route_after_retrieve(state: TicketState) -> str:
    if state["severity"] == ESCALATE_SEVERITY:
        return "escalate"
    if (state["confidence"] or 0.0) < ESCALATE_CONFIDENCE_THRESHOLD:
        return "escalate"
    return "decide"


def decide_node(state: TicketState) -> dict:
    resolution = bedrock_client.generate_resolution(
        subject=state["subject"],
        body=state["body"],
        kb_snippets=state["kb_snippets"],
        customer_context=state["customer_context"],
    )
    return {
        "resolution": resolution,
        "audit_trail": _log(state, "decide", "resolution drafted by LLM"),
    }


def respond_node(state: TicketState) -> dict:
    return {
        "escalated": False,
        "audit_trail": _log(state, "respond", "resolution returned to caller"),
    }


def escalate_node(state: TicketState) -> dict:
    reason = (
        f"severity={state['severity']} confidence={state['confidence']:.2f}"
        if state["confidence"] is not None
        else f"severity={state['severity']}"
    )
    return {
        "escalated": True,
        "escalation_reason": reason,
        "resolution": None,
        "audit_trail": _log(state, "escalate", f"handed off to human: {reason}"),
    }
