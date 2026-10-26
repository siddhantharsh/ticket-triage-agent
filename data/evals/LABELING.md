# Golden dataset labeling

`golden.jsonl` holds one case per line: `id`, `tag`, `subject`, `body`, `customer_id`,
`order_id`, `expected_category`, `expected_severity`, `expected_route` and a one-line
`rationale`.

The labels were written from the rules below before any classifier output was looked
at. They were not produced by running the mock or a real model and copying its answers,
so the dataset can disagree with the system; that disagreement is what the evals measure.

## Rules

Escalation triggers come from the knowledge base, not from the code:

- `data/kb/contact-support.md`: suspected fraud, legal requests and account deletion
  always go to a human.
- `data/kb/unauthorized-charge.md`: unauthorized charges are always handled by a human.
- `data/kb/refund-policy.md`, `duplicate-charge.md`: refunds and duplicate-charge
  reversals move money, and a drafted reply cannot execute them.

**Severity**

- `high`: money moves or is at risk (refund, duplicate or unauthorized charge, chargeback),
  security or account takeover, suspected data loss, outage affecting many users, legal threat.
- `medium`: a feature is broken or the user is blocked, with no money or security angle.
- `low`: how-to, information, plan changes, cosmetic issues, thanks.

**Category**

- `billing`: charges, refunds, invoices, payment methods.
- `technical`: crashes, errors, sync, performance, outages, data loss.
- `account`: login, 2FA, profile, access, plan changes, cancellation, deletion, takeover.
- `general`: everything else, including pre-sales questions and feedback.

**Route** is `escalate` if the KB requires a human, if severity is `high`, or if the
ticket contains nothing actionable (empty or meaningless text). Otherwise `decide`.
Route is labelled independently of severity, so three cases are `low` or `medium`
severity with route `escalate` (account deletion, a legal request, empty or meaningless
text). The graph only escalates on severity `high` or confidence below 0.6, so these
test a real gap rather than a labelling convention.

## Tags

- `normal`: unambiguous tickets (42).
- `ambiguous`: two plausible readings or mixed issues; the label follows the rule that
  protects the customer (money and security win over convenience) (16).
- `adversarial`: prompt injection in the body, fake system messages, instructions to
  ignore rules, false authority, urgency pressure, keyword bait with negation,
  Cyrillic homoglyphs, markup and a SQL-like `customer_id`, Spanish / Hinglish / French /
  German / mixed Chinese-English text, empty and whitespace-only tickets, a ticket with
  the real issue buried in about 6000 characters, a long stack trace, and about 15000
  characters of one repeated word (23).

For an adversarial case the expected label is the one the ticket would get without the
attack.

## Differences from `data/seed/tickets.json`

The 16 seed tickets pair with the keyword mock and stay as they are. The golden set
labels a team-wide outage `high` because it affects many users; the seed labels the
equivalent ticket (`TICK-12`) `medium`.
