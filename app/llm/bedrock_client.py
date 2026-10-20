import json
import os
import re
import zlib
from functools import lru_cache

import boto3

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MOCK_BEDROCK = os.environ.get("MOCK_BEDROCK", "true").lower() in ("1", "true", "yes")

CLASSIFY_CATEGORIES = ("billing", "technical", "account", "general")
CLASSIFY_SEVERITIES = ("low", "medium", "high")


@lru_cache(maxsize=1)
def _get_client():
    return boto3.client("bedrock-runtime", region_name=AWS_REGION)


def _invoke_claude(system_prompt: str, user_prompt: str, max_tokens: int = 512) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    response = _get_client().invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(response["body"].read())
    return payload["content"][0]["text"]


def _mock_confidence(text: str, base: float, spread: float) -> float:
    # Deterministic per-text jitter so mock confidence is not a handful of constants.
    unit = (zlib.crc32(text.encode()) % 1000) / 999
    return round(max(0.0, min(1.0, base + (unit * 2 - 1) * spread)), 2)


def _mock_classify(subject: str, body: str) -> dict:
    text = f"{subject} {body}".lower()

    if any(w in text for w in ("refund", "charged twice", "unauthorized", "fraud")):
        return {"category": "billing", "severity": "high", "confidence": 0.55}
    if any(w in text for w in ("breach", "hacked", "phishing", "outage")):
        return {
            "category": "technical",
            "severity": "high",
            "confidence": _mock_confidence(text, 0.7, 0.1),
        }
    if any(w in text for w in ("cancel", "downgrade", "upgrade", "plan")):
        return {
            "category": "account",
            "severity": "low",
            "confidence": _mock_confidence(text, 0.85, 0.1),
        }
    if any(w in text for w in ("broken", "crash", "error", "not working", "down ")):
        return {
            "category": "technical",
            "severity": "medium",
            "confidence": _mock_confidence(text, 0.8, 0.1),
        }
    return {
        "category": "general",
        "severity": "low",
        "confidence": _mock_confidence(text, 0.7, 0.15),
    }


def _classify_via_bedrock(subject: str, body: str) -> dict:
    system_prompt = (
        "You triage customer support tickets. Reply with ONLY a JSON object of the form "
        '{"category": "billing|technical|account|general", "severity": "low|medium|high", '
        '"confidence": <float 0 to 1>}. No other text.'
    )
    user_prompt = f"Subject: {subject}\nBody: {body}"

    try:
        raw = _invoke_claude(system_prompt, user_prompt, max_tokens=200)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = json.loads(match.group(0))

        category = parsed["category"] if parsed["category"] in CLASSIFY_CATEGORIES else "general"
        severity = parsed["severity"] if parsed["severity"] in CLASSIFY_SEVERITIES else "high"
        confidence = max(0.0, min(1.0, float(parsed["confidence"])))

        return {"category": category, "severity": severity, "confidence": confidence}
    except Exception:
        return {"category": "general", "severity": "high", "confidence": 0.0}


def classify_ticket(subject: str, body: str) -> dict:
    if MOCK_BEDROCK:
        return _mock_classify(subject, body)
    return _classify_via_bedrock(subject, body)


def _mock_generate_resolution(
    subject: str, kb_snippets: list[dict], customer_context: dict | None
) -> str:
    lead = kb_snippets[0]["text"] if kb_snippets else "No matching help-doc was found."
    tier_note = ""
    if customer_context and customer_context.get("found"):
        tier_note = f" Customer is on the {customer_context['plan_tier']} plan."
    return f"Suggested resolution for '{subject}': {lead}{tier_note}"


def _generate_resolution_via_bedrock(
    subject: str,
    body: str,
    kb_snippets: list[dict],
    customer_context: dict | None,
) -> str:
    kb_text = "\n\n".join(f"- {s['title']}: {s['text']}" for s in kb_snippets) or "None found."

    if customer_context and customer_context.get("found"):
        context_text = (
            f"Customer plan: {customer_context['plan_tier']}, "
            f"order {customer_context['order_id']} status: {customer_context['status']}"
        )
    else:
        context_text = "No customer/order record found."

    system_prompt = (
        "You are a support agent. Using the ticket, the knowledge-base snippets, and the "
        "customer/order context, write a concise, friendly 2-4 sentence resolution the agent "
        "can send to the customer. Do not invent policy details not present in the context."
    )
    user_prompt = (
        f"Subject: {subject}\nBody: {body}\n\n"
        f"Knowledge base:\n{kb_text}\n\n"
        f"Customer context:\n{context_text}"
    )

    return _invoke_claude(system_prompt, user_prompt, max_tokens=300).strip()


def generate_resolution(
    subject: str,
    body: str,
    kb_snippets: list[dict],
    customer_context: dict | None,
) -> str:
    if MOCK_BEDROCK:
        return _mock_generate_resolution(subject, kb_snippets, customer_context)
    return _generate_resolution_via_bedrock(subject, body, kb_snippets, customer_context)
