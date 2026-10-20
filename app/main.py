import logging
import time
from datetime import datetime

from fastapi import FastAPI

from app.db.triage_log import log_triage
from app.graph.build import triage_graph
from app.models.schemas import TriageRequest, TriageResponse

app = FastAPI(title="Support Ticket Triage & Resolution Agent")
logger = logging.getLogger(__name__)


def run_triage(request: TriageRequest, created_at: datetime | None = None) -> TriageResponse:
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

    started = time.perf_counter()
    result = triage_graph.invoke(initial_state)
    latency_ms = (time.perf_counter() - started) * 1000

    try:
        log_triage(result, latency_ms, created_at)
    except Exception:
        # Analytics must never fail a triage request.
        logger.exception("failed to write triage_log row for %s", request.ticket_id)

    return TriageResponse(**result)


@app.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest) -> TriageResponse:
    return run_triage(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
