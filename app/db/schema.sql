CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    plan_tier TEXT NOT NULL CHECK (plan_tier IN ('free', 'pro', 'enterprise'))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled', 'refunded')),
    amount_usd REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS triage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    category TEXT,
    severity TEXT,
    confidence REAL,
    decision TEXT NOT NULL CHECK (decision IN ('auto_resolved', 'escalated')),
    escalation_reason TEXT,
    resolution_source TEXT NOT NULL CHECK (resolution_source IN ('RAG', 'SQL', 'none')),
    latency_ms REAL NOT NULL
);
