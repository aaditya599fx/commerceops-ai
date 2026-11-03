# Live synthetic cart demonstration

The approved sample completed through real n8n intake, Gemini 3.5 Flash-Lite generation, an actual signed Slack human decision, HubSpot task creation and Google Sheets append. It used fictional customer/cart data and sent no customer email.

| Measurement | Observed result |
|---|---|
| Intake deliveries | 3: eligible cart, no-consent cart, eligible-cart replay |
| Unique events | 2 |
| Eligible completed carts | 1 of 1 |
| Policy blocks | 1: no marketing consent |
| Model calls for eligible cart | 1 |
| Model calls/effects for blocked record | 0 / 0 |
| Cart approval message | 1 recorded Slack message |
| Human decision source | Actual signed Slack HTTPS callback; authorized reviewer |
| Matching HubSpot tasks after replay | 1, independently searched and read back |
| Matching Sheets rows after replay | 1, independently counted and read back |
| Recorded effect receipts after replay | Unchanged: Slack, HubSpot, Sheets |
| Live dispatch after completion | Paused |

Actual n8n execution IDs are 273 (eligible intake), 275 (policy failure) and 300 (duplicate replay). Their metadata is in [live-n8n-executions.json](live-n8n-executions.json). Workflow execution success alone does not prove remote effects; the independent task/row checks are in [live-cart-demonstration.json](live-cart-demonstration.json).

The decision was recorded at 16:25:05 IST on November 3, 2026; completion was recorded at 16:26:05 IST. The normal .env stays in fixture mode. The demonstration used a separate live database and a dispatch guard restricted to the approved message/task/row.

During review, the temporary public tunnel returned an observed Cloudflare 530 error and later reconnected. A dashboard fallback was offered, but the real Slack callback arrived before that fallback was used. Socket Mode was investigated but was not activated for this test. Incoming HTTP callback count and individual failed-click delivery reasons were not measured.

[Live recording](live-demo.mp4) is an edited capture of the actual dashboard, with idle waits omitted. The human Slack click occurred outside the captured dashboard tab; its provenance is recorded in the durable decision/audit and remote receipts. The recording includes both the no-consent failure and duplicate suppression.

This is one live eligible cart and one policy failure. It is not a production success rate, a model-accuracy evaluation, proof of customer email delivery, or proof of Shopify-originated webhook delivery. The larger 161-event workload in [reliability.md](reliability.md) remains explicitly a fixture evaluation.
