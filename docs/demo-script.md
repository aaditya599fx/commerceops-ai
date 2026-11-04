# Demonstrations

## Live service walkthrough

[evidence/live-demo.mp4](../evidence/live-demo.mp4) is a captioned, edited screen walkthrough of actual service results using synthetic records. The first 44 seconds use dashboard captures at one frame per second from November 3. The final 28 seconds hold four actual Shopify/dashboard screenshots from November 4 for readability. Idle waits are omitted. This is not uninterrupted footage, and the human Slack click happened outside the captured dashboard tab.

1. Show the imported synthetic cart received through real n8n intake and drafted through Gemini.
2. Show the no-consent failure: blocked before model generation and outbound effects.
3. Show the actual signed human Slack decision, completed HubSpot task and Google Sheets receipt.
4. Show duplicate replay suppression and the independent one-task/one-row readbacks. Keep the sample denominators visible.
5. Show the additional user-approved Shopify synthetic product before and after saving as an unpublished Draft.
6. Show Shopify's own delivery log: products/create, 200 OK, attempt 1. Its HMAC header is excluded from the capture.
7. Show the matching Shopify-source event, validated Gemini local draft and audit trail. Source-product API readback confirms DRAFT, publishedAt null, zero price and zero quantity. No additional Slack message, HubSpot task or Sheets row was created.

The earlier failed product deliveries and tunnel outages are recorded in the verification notes. Do not present a small synthetic sample as production reliability, model accuracy, revenue lift or a performance improvement. The live model smoke sample uses Gemini 3.5 Flash-Lite; earlier OpenAI and Gemini failures remain preserved separately.

## Fixture walkthrough

[evidence/demo.mp4](../evidence/demo.mp4) is the separate deterministic fixture recording. It shows the actual n8n canvas, synthetic cart intake, dashboard approval, visibly labelled fixture receipts, duplicate suppression and a no-consent block. Its simulated provider outputs do not establish real external delivery. The 161-event reliability workload remains a fixture evaluation.
