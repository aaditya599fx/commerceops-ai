# Live integration verification

The local fixture demo and the synthetic reliability workload are separate from real-service verification. A field being present in .env is not proof of integration.

## Verified so far

- Shopify: actual shop, product, order, customer, abandoned-checkout and cart-context read queries passed. All required read scopes were granted. The configured store is not identified by Shopify as a Partner development store; this repository does not claim production Shopify experience.
- HubSpot: a clearly labelled, unassigned synthetic task was created through the real Tasks API and read back successfully. No customer contact or customer email was created.
- Slack: bot authentication and the approved connection-test message passed. The approved cart message was then sent once, and the actual authorized human click arrived as a signed HTTPS callback. Its durable decision was drained by the worker and completed the task/report actions. An observed temporary tunnel outage and missing immediate feedback caused troubleshooting; a dashboard fallback was offered but was not used. Socket Mode was investigated but no new token or receiver was created.
- Google Sheets: the API was enabled in the credentials' existing Google Cloud project. The service account can read the spreadsheet. The approved Events worksheet and headers were created, and a real append was read back. Duplicate replay left exactly one matching row.
- Public webhook transport: a self-signed synthetic probe was accepted; invalid HMAC and unauthenticated API requests were rejected. This does not verify that the secret matches Shopify or that Shopify delivered an event.
- OpenAI: authentication passed, but an actual generation request failed with credit_balance_exhausted. The latest OpenAI key no longer passes authentication and OpenAI remains optional. Gemini 3.1 Flash-Lite returned HTTP 503 UNAVAILABLE with a temporary high-demand message, and a 2.5 Flash-Lite probe returned 404. Selecting the supported Gemini 3.5 Flash-Lite model resolved generation: six synthetic workflow processor checks passed schema and local policy validation. The processor supplies the real deterministic context; no synthetic segment is hardcoded into the smoke harness. Every invocation uses an isolated database, and no outbox dispatch runs. Earlier failures are preserved in evidence/gemini31-model-smoke.json and evidence/openai-model-smoke.json. This is a small API smoke sample, not a production success rate or accuracy evaluation. There is no silent provider or fixture fallback in live mode.

The latest sanitized observations are recorded in evidence/live-readiness.json. Raw private connection details and receipts stay under ignored runtime/.

## Approval and action boundaries

Slack callbacks verify the raw body signature, timestamp and reviewer allowlist, then persist the decision and acknowledge immediately. They do not wait for the model/HTTP processing lock. The n8n dispatcher drains persisted decisions before processing the next queued event. The recorded decision timestamp is the callback receipt time rather than worker completion time.

Set ENABLE_EXTERNAL_WRITES=true only when intentionally enabling live Slack/CRM/Sheets writes. Its default is false. With live writes paused, actions remain in the durable outbox and the dispatch API reports paused. Fixture behavior is unchanged and all fixture receipts are labelled.

Do not change APP_MODE from fixture until the current blockers and intended live writes are reviewed. Use a separate DATABASE_URL for live events so fixture metrics and real-service results are not mixed.

## Shopify callbacks

python scripts/configure_webhooks.py prepares the three required subscriptions without applying them. --apply creates subscriptions only after authorization. Existing different callback URLs require review; the script does not silently delete or replace them. Mutations are not retried after an ambiguous timeout. Inspect existing subscriptions before trying again.

Order payloads include only ID, timestamps, currency and total_price. Customer contact fields are excluded. Product creation payloads include ID, title, description and created timestamp. The callback is the configured PUBLIC_BASE_URL plus /webhooks/shopify. A temporary tunnel URL must be kept running; a new URL requires updating subscriptions deliberately.

After the user explicitly approved the data and Cloudflare destination, all three minimal subscriptions were created successfully. Signed delivery from Shopify is still unverified.

Order callbacks are deduplicated by delivery ID and content hash. Reusing an ID with different content is rejected. Older updated_at values do not overwrite newer order facts. Incomplete product events return 422 instead of an unhandled exception.

## Business metric definitions

order_value_total is the sum of source order total_price in each currency. It is not gross merchandise sales: source totals can include discounts, shipping and taxes. Average order value divides these order totals by the count of ingested orders. Missing refund details are reported as unknown, not zero. These metrics describe ingested facts, not a complete financial ledger.

## Completing the live demonstration

1. Model generation is verified on a six-workflow synthetic sample using Gemini 3.5 Flash-Lite. Complete the real human decision and remote action checks below before declaring full live integration.
2. The Events worksheet and one approved synthetic append/readback are verified.
3. Actual Slack HTTPS review is verified for the one approved synthetic cart; its remote task and report receipts were read back. Keep this separate from large-sample reliability.
4. Verify an actual Shopify delivery through the approved subscriptions without creating or modifying live customer records.
5. The approved synthetic cart path, actual human Slack decision, task/report readbacks, duplicate replay and no-consent policy failure are recorded in evidence/live-cart-demonstration.json. The live edited screen recording is evidence/live-demo.mp4.
6. Preserve raw denominators and failures. Do not turn a successful auth probe or self-signed transport test into a claim of complete live integration.

## Completed live cart sample

The sample used two unique imported synthetic records and one duplicate delivery. One eligible cart completed, one no-consent record was blocked, one model call was recorded for the eligible cart, and zero model calls/effects were recorded for the blocked record. HubSpot search and Sheets reads each returned one matching remote record after replay. The final live demo server reports external writes paused. The normal .env remains in fixture mode; the scoped demonstration used a separate live database.

The decision source was the real Slack HTTPS callback, not a local dashboard click or a self-signed emulation. Incoming callback count was not measured. The editor captures are an edited walkthrough with idle waits omitted; the human click happened outside the recorded dashboard tab and is evidenced by the signed callback, durable decision and downstream receipts.
