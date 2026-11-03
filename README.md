# CommerceOps AI

A human-supervised commerce operations system: store signals become validated drafts, exception alerts, CRM follow-up tasks and traceable reports.

**Current evidence:** running local FastAPI application, durable SQLite state, six implemented workflows, nine workflows imported into and exported from n8n, and a measured synthetic evaluation. Shopify/Slack/HubSpot/Sheets integration is pending credentials and actual end-to-end verification. OpenAI authentication was verified, but the real generation smoke test returned HTTP 429 for all six workflows and failed closed; no successful live generation is claimed. This is a portfolio simulation, not a CommerceV3 internal system.

![Operations dashboard](evidence/dashboard.png)

[Recorded demonstration](evidence/demo.mp4) · [Measured reliability](evidence/reliability.md) · [Raw measurements](evidence/reliability.json) · [Setup](docs/setup.md) · [Runbook](docs/runbook.md)

## Run locally

Requires Python 3.11–3.13. From the repository directory:

```bash
./scripts/start.sh
```

Open http://localhost:8000 and enter `APP_TOKEN` from the generated `.env`. The default `fixture` mode uses fictional records and deterministic provider responses. The Python API, schema validation, SQL persistence, approvals, audit trail and failure handling are real. No customer email is sent. Fixture Slack/HubSpot/Sheets action receipts are visibly labelled `fixture:`.

Click **Eligible cart**, inspect the draft, then approve or reject. Click **Replay last event** to demonstrate duplicate suppression, or **No-consent case** to see a policy block. The other sample buttons exercise inventory, reviews, product drafts, customer segmentation and executive reporting.

## Architecture

```mermaid
flowchart LR
  S[Shopify signed webhooks / checkout polling] --> Q[Durable event intake]
  W[n8n authenticated webhooks] --> Q
  Q --> N[n8n process / scheduled dispatcher]
  N --> B[Python policies and calculations]
  B --> L[OpenAI structured outputs]
  L --> V[Schema and policy validation]
  V --> A[Slack human approval for cart draft]
  A --> O[Durable action outbox]
  V --> O
  O --> H[HubSpot follow-up task]
  O --> G[Google Sheets append]
  B --> D[(SQLite locally / PostgreSQL option)]
  O --> D
  D --> U[Audit and metrics dashboard]
```

The backend can run its single-process worker by default, so the application works without n8n. Set `WORKER_ENABLED=false` when using n8n as the orchestration owner. n8n acknowledges only after database intake, skips duplicate deliveries, invokes the bounded processor, branches on validation failure and dispatches persisted actions. Signed Shopify webhooks enter Python directly to preserve raw-body signature verification; n8n's scheduled dispatcher drains that queue.

## Workflows

| Workflow | Deterministic work | Model task / output | Action boundary |
|---|---|---|---|
| Cart recovery | Consent, item totals, minimum value, purchase check, cooldown | Neutral structured recovery draft | Human approval before CRM draft; never sends email |
| Inventory watch | Days of cover and reorder units | Summary and recommendation | Alert only; no purchase orders |
| Review intelligence | Input/rating validation | Sentiment, category, urgency, source quote | Urgent Slack alert and support task |
| Product growth | Source grounding and JSON-LD assembly | Extractive SEO/meta/FAQ draft | Saved for editing; never publishes |
| Customer intelligence | First-time/repeat/high-spend/dormant/at-risk segment | Explanation and suggestion | CRM follow-up task |
| Executive brief | Currency-separated order totals, refunds, AOV | Narrative based on supplied metrics | Spreadsheet log; source record IDs retained |

`workflows/` contains actual n8n CLI exports. Six event workflows plus a queue dispatcher, Shopify checkout poll and daily 09:00 Asia/Kolkata brief schedule. Imported workflows are disabled by default in a fresh install; publish intentionally after configuring credentials. `scripts/build_workflows.py` creates import candidates under ignored `runtime/import/`, not exported evidence.

![Actual n8n workflow](evidence/n8n-cart.png)

## Real integrations

Fill `.env` locally, run read-only probes with `python scripts/check_connections.py`, then follow [the live setup checklist](docs/setup.md). Switch to `APP_MODE=live` only after configuring the intended services. Missing credentials fail closed; live mode never falls back to fixtures.

- Shopify: raw-body HMAC plus exact shop-domain verification; signed order/product webhooks; Admin GraphQL shop probe, current customer consent/purchase context and paginated abandoned-checkout polling. Inventory requires a supplied sales-velocity/lead-time input; these numbers are never fabricated.
- OpenAI: Responses API, strict JSON Schema, `store=false`, bounded timeout/retries and local validation. Prompt is versioned in `prompts/`. Email and customer IDs are omitted from model input.
- Slack: Web API approval messages; signed interactive callbacks; five-minute signature age limit; explicit reviewer ID allowlist.
- HubSpot: real Tasks API. Customer communications remain internal CRM drafts. No automated email channel is implemented.
- Google Sheets: service-account authentication, real append API, `RAW` values to prevent formula interpretation.

## Validation and honest metrics

```bash
python -m pytest -q
python scripts/evaluate.py
```

The recorded fixed workload used **161 unique synthetic events**, **152 completed eligible runs**, **9 policy-blocked runs**, **30 suppressed duplicate deliveries**, and **0 duplicate recorded action keys**. Full denominators and limitations are in `evidence/reliability.json`. Fixture schema validity is not evidence of model quality. The attempted real-model smoke check is preserved in [live-model-smoke.json](evidence/live-model-smoke.json), including failures. External delivery is not guaranteed exactly once. Human approval time, model classification accuracy, monetary cost, time savings and revenue lift have not been measured.

Failure tests include absent consent, changed consent, recent purchase, cooldown, rejected approval, malformed output, unsafe copy, API rate limiting/outage, invalid signatures, unauthorized reviewers, ambiguous remote writes and restart recovery. See `evidence/pytest.txt` for the executed test result.

## Limits

Use one API/worker process; the current worker uses an in-process execution lock. PostgreSQL connection support and Docker Compose are supplied but were not exercised on this host. Remote write timeouts are held for manual reconciliation rather than automatically repeated. An interrupted external call can have succeeded remotely; inspect the source service before taking further action. No Shopify production experience, live reliability or business impact is claimed by this repository.

Product copy is intentionally extractive to make factual grounding enforceable. SEO ranking gains are unmeasured. Executive business metrics use ingested order facts; they are not a complete accounting ledger. Currency conversions, tax treatment, broad historical backfill and production multi-tenant isolation are outside the current MVP.

## Repository

`backend/` application and adapters · `workflows/` n8n exports · `data/` fictional records · `prompts/` versioned prompt · `tests/` behavioral and failure tests · `docs/` setup and runbooks · `evidence/` demonstration and actual measurements.
