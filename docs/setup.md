# Setup and live verification

## Local app

Run `./scripts/start.sh`. It creates `.venv`, installs pinned Python requirements, creates a private `.env` with a random local bearer token and starts the app at http://localhost:8000. All `/api/*` endpoints require that bearer token. Keep the API bound to loopback while configuring services.

Use one Uvicorn worker. `WORKER_ENABLED=true` is the default. The database is `runtime/commerceops.db`; restart preserves events, approvals and audit records. Use a separate database when changing fixture/live modes so synthetic history is not mixed with live history.

## Secret fields

Do not commit `.env`, service-account JSON, databases, n8n credentials or connection logs. `.gitignore` and `.dockerignore` exclude these. Save Google credentials outside the repo and set the absolute `GOOGLE_SERVICE_ACCOUNT_FILE` path. No private token belongs in a workflow export.

| Service | Fields | Setup |
|---|---|---|
| Gemini | LLM_PROVIDER=gemini, GEMINI_API_KEY, GEMINI_MODEL | Create a key in Google AI Studio; default gemini-3.5-flash-lite. Free tier has limits and content may improve Google products; use synthetic demo inputs |
| OpenAI (alternative) | OPENAI_API_KEY, OPENAI_MODEL | Set LLM_PROVIDER=openai and use an API key with credits; default gpt-4.1-mini |
| Shopify | SHOPIFY_SHOP, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET, SHOPIFY_WEBHOOK_SECRET | Development store, `read_orders`, `read_customers`, `read_products` and abandoned-checkout permission as required; confirm protected-customer-data access |
| Slack | SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_CHANNEL_ID, SLACK_APPROVER_IDS | Dedicated test channel; bot invited with chat:write; comma-separated authorized reviewer IDs |
| HubSpot | HUBSPOT_ACCESS_TOKEN, optional HUBSPOT_OWNER_ID | Test account Service Key with task-write permissions appropriate to the account |
| Sheets | GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SPREADSHEET_ID, GOOGLE_SHEET_RANGE | Enable Sheets API; share spreadsheet with service account; create `Events` worksheet |
| n8n | N8N_BASE_URL, optional N8N_API_KEY | Local instance or cloud; API key is needed for API-managed import/export, not backend processing |

For Gemini, create a key at https://aistudio.google.com/api-keys and save it as GEMINI_API_KEY locally. Its free tier is subject to availability and project quotas; no unlimited or permanent free usage is promised. Pricing: https://aistudio.google.com/docs/pricing. Keep APP_MODE=fixture while preparing credentials. The connection checker probes only the selected model provider. It does not fall back to another provider or to fixtures.

For Sheets, open the actual spreadsheet, click Share, add the service account client_email, choose Editor and share. Keep General access Restricted. Spreadsheet sharing is separate from Google Cloud project IAM; project-wide Editor access is unnecessary. Create a worksheet named Events.

Run `python scripts/check_connections.py`. Probes only read authentication; they do not post messages, create CRM tasks, append sheet rows or prove webhook delivery. Results are written to ignored `runtime/connections.json`.

For a live workflow test, use a dedicated test Slack channel and HubSpot account. Inspect the exact synthetic event and proposed draft first, then authorize the test messages/writes. Record the real execution IDs and remote task/sheet receipts; a filled field alone is not integration evidence.

## n8n

Verified export format: n8n 2.4.4. Install using the supplied locked npm dependencies or Docker image. The npm lock pins a compatible LangGraph checkpoint dependency; unconstrained upstream ranges can otherwise break startup.

```bash
npm ci --legacy-peer-deps
export COMMERCEOPS_API_URL=http://127.0.0.1:8000
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export GENERIC_TIMEZONE=Asia/Kolkata
npx n8n import:workflow --separate --input=workflows
npx n8n start
```

Create n8n's local owner account. Create a **Header Auth** credential named `CommerceOps API bearer`, header name `Authorization`, value `Bearer <APP_TOKEN>`. Select that credential on each Webhook/HTTP Request node referencing it. Exported credential IDs are references, not portable secrets; reselect after import when needed.

Publish the six event workflows and the durable queue dispatcher. Publish the Shopify poll only in configured live mode. Publish the daily brief if you want the daily 09:00 Asia/Kolkata schedule. Set backend `WORKER_ENABLED=false` to make n8n the processing owner.

Send an envelope from `data/events.json` to `POST http://localhost:5678/webhook/commerceops/cart` (or inventory/review/product/customer/brief), with `Authorization: Bearer <APP_TOKEN>`. The workflow acknowledges database intake with HTTP 202, then processes asynchronously. Inspect n8n executions and `/api/runs/{event_id}` for completion. An accepted webhook response does not prove a completed workflow.

Export after every n8n editor change:

```bash
npx n8n export:workflow --all --separate --output=workflows
```

Never use decrypted credential export in this repository. Re-run secret scanning before pushing.

## Shopify and Slack callbacks

Expose only required callback routes on a stable HTTPS URL using your hosting provider or tunnel. Set `PUBLIC_BASE_URL`. Keep the dashboard/API bearer-protected. Register Shopify `orders/create`, `orders/updated` and `products/create` webhooks at `/webhooks/shopify`; the secret must match that webhook's signing configuration. Shopify abandonment is polled through GraphQL; there is no invented `cart.abandoned` Shopify webhook topic.

Set Slack interactivity Request URL to `/webhooks/slack/actions`. Approve/reject actions require a valid Slack signature and a reviewer in `SLACK_APPROVER_IDS`. Callback acknowledgement has no outgoing API writes; the outbox worker completes follow-up actions. Record an actual signed callback before claiming the approval integration is complete.

Shopify cart polling is paginated at 50 checkouts per poll. It ignores completed checkouts, carts updated less than an hour ago and carts requiring more than 100 line items. It refreshes current consent/purchase context before drafting and before creating an approved CRM draft. Checkout totals use original line-item value for eligibility; no discount is inferred. Document this choice to reviewers.

## PostgreSQL / containers

Docker was not installed on the build host; this path is provided but not yet verified. Add random `POSTGRES_PASSWORD` and `N8N_ENCRYPTION_KEY` values to `.env`, then `docker compose up --build`. It creates PostgreSQL, API and n8n containers, exposing only loopback ports. Import and publish workflows as above, selecting the Header Auth credential. Mount Google credential JSON read-only and use its in-container path. Treat internet deployment, TLS, backups, rate limiting, least-privilege ingress and production operations as a separate setup step.

## GitHub

Authenticate using `gh auth login` on your computer. From this repository directory:

```bash
gh repo create commerceops-ai --private --source=. --remote=origin --push
```

The repository includes exported n8n workflows and CI, not secrets or runtime state. Repository creation and push must actually succeed before claiming it is on GitHub.

New Shopify Dev Dashboard apps exchange Client ID/Client Secret for a token automatically; app and store must be in the same Shopify organization. A supplied SHOPIFY_ACCESS_TOKEN overrides this flow. Use the app Client Secret as SHOPIFY_WEBHOOK_SECRET for app-configured webhooks. New HubSpot integrations use Service Keys (Settings > Integrations > Service Keys), not new legacy private apps. Existing legacy private-app tokens remain compatible.

## Live action enablement and evidence

ENABLE_EXTERNAL_WRITES defaults to false. Enable it deliberately after approving the intended Slack/CRM/Sheets test actions. Read-only probes update credential-bound private connection evidence, and the dashboard shows read, generation and write phases separately. Changing credentials invalidates old connection evidence; checks older than 24 hours are hidden. See docs/live-verification.md for the current blockers and verification boundaries.
