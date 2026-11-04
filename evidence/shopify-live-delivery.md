# Genuine Shopify product webhook — November 4

The user approved one additional synthetic unpublished Draft after the original test exhausted delivery retries. Shopify product `10385063870681` was saved with title “CommerceOps synthetic webhook test — 2026-11-04”. The app accepted its genuine signed products/create delivery and produced a local Gemini content draft through the n8n dispatcher.

| Measurement | Observed result |
|---|---|
| Fresh synthetic products created in this test | 1 |
| Shopify delivery result | 200 OK, attempt 1 |
| Provider-reported response time | 649 ms for this delivery only |
| Minimal payload size | 278 bytes |
| Webhook ID | a6696798-c816-5643-99a5-2432440d8698 |
| Received at app | 2026-11-04T04:00:56.759222Z |
| Local draft saved | 2026-11-04T04:01:04.715555Z |
| Actual n8n dispatcher execution | 1049, success, processed count 1 |
| Model calls | 1, Gemini 3.5 Flash-Lite, schema/policy valid |
| Source product readback | DRAFT, publishedAt null, price 0, quantity 0 |
| Slack / HubSpot / Sheets effects | 0 / 0 / 0 |
| External write setting after completion | Paused |

[Raw verification](shopify-live-delivery.json) · [n8n execution correlation](shopify-n8n-execution.json) · [Shopify delivery log](shopify-delivery-200.jpg) · [actual local result](shopify-live-result.jpg) · [combined live walkthrough](live-demo.mp4).

The n8n worker response records a processed count, not event IDs. Its execution interval overlaps the backend audit for the single queued Shopify event. Backend workers were disabled and the published n8n dispatcher owned this queue. The input's Shopify provenance is established by the signed ingress, exact shop check, product ID readback and matching Shopify delivery log, rather than a self-signed local probe.

The still-active previous app secret verified the real signature, confirming the rotation fix. The original November 3 Draft remains unpublished; its failed deliveries are preserved as a separate failure history. Two temporary tunnel addresses expired before the final recovery. These failures are not erased by the new success.

This is one successful synthetic product event. The earlier cart demonstration is a separate live sample using imported synthetic data. Actual order-created/updated delivery, recovery of a real abandoned checkout, production reliability, model accuracy and business impact were not established. A single 649 ms response is not a latency benchmark or a performance improvement. The temporary public endpoint still depends on the Mac and tunnel staying available.
