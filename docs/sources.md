# Implementation references

Reviewed against official documentation during the build:

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs): Responses API `text.format`, JSON Schema, strict validation.
- [n8n Server CLI](https://docs.n8n.io/hosting/cli-commands/): import/export/publish workflow commands. Local tested release: 2.4.4.
- [Shopify webhook verification](https://shopify.dev/docs/apps/build/webhooks/verify-deliveries): raw-body HMAC and duplicate handling.
- [Shopify abandoned checkouts](https://shopify.dev/docs/api/admin-graphql/latest/queries/abandonedCheckouts): permissions and pagination.
- [Shopify checkout line items](https://shopify.dev/docs/api/admin-graphql/latest/objects/AbandonedCheckoutLineItem): source quantities and money fields.
- [Slack signed requests](https://docs.slack.dev/authentication/verifying-requests-from-slack/): timestamp and raw-body signature verification.
- [HubSpot Tasks API](https://developers.hubspot.com/docs/api-reference/legacy/crm/activities/tasks/guide): task properties and create endpoint.
- [Google Sheets append API](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append): append requests and RAW input.

The supplied blueprint informed feature scope. Its portfolio and résumé suggestions are conditional; they are not evidence of completed integration or business results.
