from pydantic import BaseModel


class TriageRequest(BaseModel):
    ticket_id: str
    subject: str
    body: str
    customer_id: str | None = None
    order_id: str | None = None


class AuditEntryResponse(BaseModel):
    node: str
    summary: str
    timestamp: str


class KBSnippetResponse(BaseModel):
    doc_id: str
    title: str
    text: str
    score: float


class CustomerContextResponse(BaseModel):
    customer_id: str | None
    order_id: str | None
    status: str | None
    plan_tier: str | None
    found: bool


class TriageResponse(BaseModel):
    ticket_id: str
    category: str | None
    severity: str | None
    confidence: float | None
    kb_snippets: list[KBSnippetResponse]
    customer_context: CustomerContextResponse | None
    resolution: str | None
    escalated: bool
    escalation_reason: str | None
    audit_trail: list[AuditEntryResponse]
