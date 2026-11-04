# Live integration verification

The working MVP has real service integrations verified on small synthetic samples. Fixture evaluation, API authentication, model smoke checks and live workflow completion have separate evidence. A populated .env is not proof of integration.

## Current verified results

- Shopify: actual shop, product, order, customer, abandoned-checkout and cart-context reads passed with the required read scopes. A genuine products/create delivery from the approved synthetic Draft passed raw-body HMAC and exact-shop verification. Shopify reported 200 OK on attempt 1. Actual n8n dispatcher execution 1049 processed one queued event; Gemini produced a validated local content draft. Readback confirmed the source product remained DRAFT, publishedAt null, price 0 and quantity 0. See [product verification](../evidence/shopify-live-delivery.md).
- Gemini: all six workflow processors passed the earlier real Gemini 3.5 Flash-Lite synthetic schema/policy smoke sample. The eligible live cart and genuine Shopify product each recorded one valid model call. No live-mode fixture or provider fallback occurs.
- Slack: bot authentication and the approved test message passed. The approved cart message was sent once, and an actual authorized human click arrived as a signed HTTPS callback. Its durable decision completed the task/report actions. The callback used the earlier public URL. The new URL has been saved and read back, but no additional human click was requested to retest that URL. Socket Mode was investigated; no new token or receiver was created.
- HubSpot: synthetic internal Tasks API writes and independent readbacks passed. The approved live cart had exactly one matching task after duplicate replay. No customer email was sent.
- Google Sheets: service-account file access, the approved Events tab/header setup, append and readback passed. The approved live cart had exactly one matching report row after replay.
- Current public transport: anonymous health returned 200; invalid Shopify signatures and unauthenticated private API requests returned 401. APP_TOKEN was used only on loopback, never through Cloudflare. The successful genuine Shopify delivery separately proves provider-originated ingress.

The configured Shopify store is not identified as a Partner development store. Actual integration is established; production Shopify experience is not claimed. [Current sanitized readiness](../evidence/live-readiness.json) and ignored private runtime connection checks bind observations to the configured credentials.

## Completed live demonstrations

The cart sample used two imported synthetic records and one duplicate delivery: one eligible cart completed, one no-consent record was blocked, and one replay was suppressed. The eligible cart recorded one model call and Slack/HubSpot/Sheets receipts; the blocked record recorded zero model calls and effects. Independent remote reads each confirmed one matching task and row. The human decision came through the actual signed Slack callback; the offered dashboard fallback was not used. See [cart measurements](../evidence/live-cart-demonstration.md).

The separate Shopify sample used one additionally approved synthetic product, 10385063870681. Its webhook ID a6696798-c816-5643-99a5-2432440d8698 matches the Shopify delivery log and app event. The event was received at 2026-11-04T04:00:56.759222Z and the local draft was saved at 04:01:04.715555Z. The n8n worker response records a processed count, so execution 1049 is correlated by its overlapping interval and the single queued product rather than an event ID returned by n8n. This product path created zero Slack, HubSpot or Sheets effects. See [raw product verification](../evidence/shopify-live-delivery.json) and [n8n correlation](../evidence/shopify-n8n-execution.json).

[The 72-second live walkthrough](../evidence/live-demo.mp4) includes cart approval, the no-consent failure, duplicate suppression and the successful Shopify test. It uses actual UI captures with captions and idle waits omitted; four Shopify screenshots are held for readability. The human Slack click occurred outside the captured dashboard tab and is evidenced by the signed callback, durable decision and remote receipts. It is not uninterrupted footage. The separate fixture recording and 161-event workload remain explicitly synthetic evaluations.

## Failure history and recovery

The first approved synthetic Draft, 10381782974681, remains unpublished. Its initial genuine deliveries were rejected with 401: the exact shop matched, but Shopify signed with the previous still-active secret while only the new secret was configured. The adapter now accepts the explicitly configured current/previous pair while preserving exact raw-body and shop checks. The successful November 4 delivery verified the still-active previous secret. No secret was rotated or revoked by the app.

The original and first replacement Cloudflare Quick Tunnels expired. URL renewal stopped partway through a timed-out mutation; independent readback identified two changed order subscriptions and the unchanged product subscription. The original product exhausted nine attempts, ending with Invalid webhook URL at 2026-11-03T15:27:14Z. No manual redelivery control was available in the inspected log view.

The user then selected a new temporary tunnel and explicitly approved one additional Draft. All three Shopify callbacks, Slack interactivity and local PUBLIC_BASE_URL were moved to https://rest-lite-char-tax.trycloudflare.com and read back. The minimal field lists were unchanged. The fresh test succeeded; no further product was created. The callback recovery utility validates all subscriptions and destination health before mutation, supports explicitly listed previous addresses, and does not retry ambiguous writes. See [recovery evidence](../evidence/callback-recovery.json).

Earlier provider failures remain preserved. OpenAI generation failed on exhausted credits and its later key failed authentication; OpenAI is optional. Earlier Gemini probes returned 503 or an unsupported-model 404. Selecting the available Gemini 3.5 Flash-Lite resolved generation. A successful later sample does not erase those failures or establish ongoing free quota.

## Action boundaries and operations

External writes default to paused. Slack callbacks validate signature, timestamp and reviewer allowlist, persist the decision, and acknowledge without waiting for model processing. The n8n dispatcher drains persisted decisions before queued events. Ambiguous external writes are held for reconciliation rather than blindly retried. Use one API/worker owner; distributed leases are outside this MVP.

The regular .env remains in fixture mode. The scoped live demo uses a separate database and guards the one approved cart message/task/row. Live outbound writes are paused after completion. Product generation produces a local editorial draft and never publishes it. Enable additional live actions only for their intended scope. The local server, tunnel and n8n must remain running for this temporary setup.

Shopify order payloads contain only ID, timestamps, currency and total_price. Product payloads contain ID, title, description and created timestamp. Order deliveries are deduplicated by delivery ID/content hash; older updated_at values cannot overwrite newer facts. Incomplete product events return 422. Subscription configuration and URL renewal are separate deliberate commands; neither creates a store test product.

## Measurement limits

The live evidence covers one imported eligible cart, one policy failure, one replay, and one successful genuine Shopify product event. Real abandoned-checkout recovery and actual order-created/updated delivery were not exercised. The other workflows have implementation tests and a real-model synthetic sample, not complete production validation.

The 161-event fixture workload does not establish live service reliability, model accuracy, throughput, financial cost, time savings or revenue lift. Shopify's 649 ms response is one provider observation, not a benchmark or an improvement claim. Temporary tunnel outages were observed and stable hosting has not been configured.

Business metrics use ingested order total_price per currency. These totals may include discounts, shipping and taxes; they are not gross merchandise sales. Missing refund information remains unknown. Historical backfill, currency conversion, complete financial accounting and production multi-tenant isolation are outside the MVP.
