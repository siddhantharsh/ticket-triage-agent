from fastapi import FastAPI

from app.graph.build import triage_graph
from app.models.schemas import TriageRequest, TriageResponse

app = FastAPI(title="Support Ticket Triage & Resolution Agent")


@app.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    initial_state = {
        "ticket_id": request.ticket_id,
        "subject": request.subject,
        "body": request.body,
        "customer_id": request.customer_id,
        "order_id": request.order_id,
        "category": None,
        "severity": None,
        "confidence": None,
        "kb_snippets": [],
        "customer_context": None,
        "resolution": None,
        "escalated": False,
        "escalation_reason": None,
        "audit_trail": [],
    }

    result = triage_graph.invoke(initial_state)
    return TriageResponse(**result)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
