# Live integration verification

The local fixture demo and the synthetic reliability workload are separate from real-service verification. A field being present in .env is not proof of integration.

## Verified so far

- Shopify: actual shop, product, order, customer, abandoned-checkout and cart-context read queries passed. All required read scopes were granted. The configured store is not identified by Shopify as a Partner development store; this repository does not claim production Shopify experience.
- HubSpot: a clearly labelled, unassigned synthetic task was created through the real Tasks API and read back successfully. No customer contact or customer email was created.
- Slack: bot authentication passed and the one explicitly approved synthetic test message was sent successfully. This does not verify interactive callbacks.
- Google Sheets: the API was enabled in the credentials' existing Google Cloud project. The configured spreadsheet now passes a read-only service-account probe. The configured Events worksheet is absent and needs creating. A synthetic append is still unverified.
- Public webhook transport: a self-signed synthetic probe was accepted; invalid HMAC and unauthenticated API requests were rejected. This does not verify that the secret matches Shopify or that Shopify delivered an event.
- OpenAI: authentication passed, but an actual generation request failed with credit_balance_exhausted. The latest key no longer passes authentication. OpenAI remains optional; Gemini support has been added for the requested free-tier alternative, with no verified Gemini generation yet: all six initial synthetic workflow calls failed with upstream server errors. A separate model lookup passed authentication, and a minimal generation request returned HTTP 503 UNAVAILABLE with a temporary high-demand message. A single alternative 2.5 Flash-Lite probe returned 404; the configured model remains 3.1 Flash-Lite. There is no silent provider or fixture fallback in live mode.

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

1. Save a Gemini API key and verify a small synthetic structured-output sample (or fund the optional OpenAI provider).
2. Verify the Events tab and one clearly labelled synthetic append; spreadsheet read access now passes.
3. Configure the Slack interactive callback URL and verify an actual signed callback; the approved test message is already sent.
4. Verify an actual Shopify delivery through the approved subscriptions without creating or modifying live customer records.
5. Run the approved cart path, record a real human decision and CRM/Sheets receipts, and replay the event to show duplicate suppression.
6. Preserve raw denominators and failures. Do not turn a successful auth probe or self-signed transport test into a claim of complete live integration.
