# Operations and failure runbook

## Inspect a failure

Open the control room or `GET /api/runs/{event_id}` with the bearer token. Follow timestamps, status, policy reason, model/output error category and action receipts. Error categories are stored instead of upstream response bodies so secrets are not logged.

- `blocked`: deterministic eligibility gate; no draft/contact action. Review consent, purchase history, minimum value or cooldown. A changed payload requires a new event ID.
- `awaiting_approval`: validated cart draft; no CRM follow-up task has been created yet. An authorized operator may approve/reject in the dashboard or through a signed Slack callback.
- `dead_letter`: model timeout/refusal, malformed output, unsafe language or an internal processing failure. Fix the cause, then `POST /api/runs/{id}/replay`. Only dead-letter events are replayable; at most three processing attempts.
- `held`: external action failed or may have succeeded remotely. Do not replay it blindly. Inspect Slack/HubSpot/Sheets for the event ID, reconcile the remote receipt, then repair only that persisted effect under operator control. There is no automatic retry endpoint for uncertain remote writes.
- `draft_ready`: editorial product draft saved; nothing has been published.
- `completed`: required recorded effects are done. In fixture mode this means fixture receipts, not real third-party delivery.

## Retry policy

Read-only HTTP requests and model calls use at most three transport attempts for timeouts, network errors, HTTP 429 and 5xx. Delay uses bounded Retry-After/backoff. Permanent 4xx errors are not retried. Malformed model output is retried once. Outbound side-effect writes have one attempt; ambiguous results become `uncertain` and require reconciliation.

Database unique constraints protect `(event_id, effect_kind)`. Duplicate event IDs with identical content are suppressed. Reusing an ID with different data is HTTP 409. Repeated identical approvals are safe. A contradictory decision after resolution is HTTP 409.

## Restart

Run one API process. Restart the server and n8n. In-progress event processors return to `queued`; interrupted `sending` actions become `uncertain` and their runs are held. This favors an inspectable hold over a duplicate action. Do not run two application worker processes against the same state; distributed job leases are not implemented.

## Metrics

`GET /api/metrics` returns counts and explicit denominators. Successful means completed/draft-ready; eligible excludes policy-blocked and rejected events. Queued, pending-approval, held and dead-letter eligible events remain in the denominator. Keep fixture/live data in separate databases. Model schema pass rate counts parsed model outputs including invalid outputs, with a separate live-only value; transport failures are not model outputs. Recorded effect uniqueness is not proof of exactly-once delivery at external APIs. Cost, quality, business impact and human-review time require separate measurements.

## Data and security limits

Synthetic fixtures are safe for public examples. Live event payloads and CRM tasks can contain personal data; databases are local private state and must not be committed. The MVP does not supply tenant separation, automatic retention/deletion, full access-role management or account compliance workflows. Do not enable a production Shopify public app without implementing its required privacy and operational lifecycle. Tokens are local environment values, never part of an export or screenshot.

Slack callbacks acknowledge after queuing a durable decision. The dispatcher drains decisions before processing more events. In live mode, outbound writes remain paused unless ENABLE_EXTERNAL_WRITES=true. An empty queue is not proof of successful third-party delivery.
