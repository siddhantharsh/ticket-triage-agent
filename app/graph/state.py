from typing import TypedDict


class AuditEntry(TypedDict):
    node: str
    summary: str
    timestamp: str


class KBSnippet(TypedDict):
    doc_id: str
    title: str
    text: str
    score: float


class CustomerContext(TypedDict):
    customer_id: str
    order_id: str | None
    status: str | None
    plan_tier: str | None
    found: bool


class TicketState(TypedDict):
    ticket_id: str
    subject: str
    body: str
    customer_id: str | None
    order_id: str | None

    category: str | None
    severity: str | None
    confidence: float | None

    kb_snippets: list[KBSnippet]
    customer_context: CustomerContext | None

    resolution: str | None
    escalated: bool
    escalation_reason: str | None

    audit_trail: list[AuditEntry]
