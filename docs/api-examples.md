# API examples

All sample records are fictional. Keep secrets in local environment variables. API documentation is at `/docs`; requests require `Authorization: Bearer <APP_TOKEN>`.

```bash
# Choose an envelope from data/events.json and save as runtime/cart.json.
curl http://localhost:8000/api/events \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H 'Content-Type: application/json' --data-binary @runtime/cart.json

curl -X POST http://localhost:8000/api/runs/sample-00/process \
  -H "Authorization: Bearer $APP_TOKEN"

curl http://localhost:8000/api/runs/sample-00 \
  -H "Authorization: Bearer $APP_TOKEN"

curl -X POST http://localhost:8000/api/runs/sample-00/decision \
  -H "Authorization: Bearer $APP_TOKEN" -H 'Content-Type: application/json' \
  -d '{"decision":"approve","reason":"Reviewed consent and neutral copy."}'

curl -X POST http://localhost:8000/api/actions/dispatch \
  -H "Authorization: Bearer $APP_TOKEN"
```

Change the event ID in these routes to match your envelope. `/api/events` returns a durable intake acknowledgement, not completion. `/api/runs/{id}/process` returns the inspected run after bounded processing; outbox dispatch is separate. Production-style n8n webhooks acknowledge after database intake and continue processing asynchronously.

For the n8n path, send the same JSON envelope to `/webhook/commerceops/cart` on port 5678 with the same Header Auth value. Repeating the identical event creates no second run. An ID reused with different data returns 409.

`POST /api/seed` and `/api/demo/events` are fixture-only. Shopify data cannot be spoofed through `/api/events` using source `shopify`; verified webhook ingress or the Shopify API poll is required.
