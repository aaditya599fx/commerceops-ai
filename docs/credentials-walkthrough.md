# Credentials walkthrough

Keep APP_MODE=fixture until the live integration checks pass. Fill secrets only in the local .env file.

## Open the configuration

```bash
cd "/Users/aad1tyayadav/Documents/Codex/2026-11-03/i-w/outputs/commerceops-ai"
open -a TextEdit .env
# Alternative terminal editor:
nano .env
```

Nano: Control+O, Enter to save; Control+X to exit. Preserve APP_TOKEN and DATABASE_URL. Leave values after `=` and retain each variable name.

## OpenAI

1. Open https://platform.openai.com/api-keys and choose your API project.
2. Create a secret key if needed. Save it as OPENAI_API_KEY.
3. Keep OPENAI_MODEL=gpt-4.1-mini unless changing to another supported structured-output model.
4. Check API organization credits and model limits. The recorded real-generation smoke test returned HTTP 429; a successful auth probe does not prove generation is available.
5. Eligible ChatGPT plans can claim API credits by linking an API organization; otherwise configure API billing separately.

Sources: https://developers.openai.com/api/docs/quickstart and https://developers.openai.com/api/docs/guides/chatgpt-api-credits

## Shopify development store

1. Open https://dev.shopify.com and use a development store in the same organization as the app.
2. Apps > Create app > Start from Dev Dashboard. Name it CommerceOps AI.
3. In Versions, create a version. For a nonembedded app, Shopify permits the default home URL https://shopify.dev/apps/default-app-home.
4. Request read_orders, read_customers and read_products. Use 2026-10 API/webhook version where available. Release the version.
5. Install the app on your own development store and approve the scopes. Customer data and abandoned-checkout permissions may require additional access.
6. Open app Settings/App settings > Credentials. Copy Client ID and Client Secret into SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET.
7. Set SHOPIFY_SHOP to your exact store domain, such as your-store.myshopify.com (no protocol or path).
8. For app-configured webhooks, set SHOPIFY_WEBHOOK_SECRET to the same app Client Secret. Admin-created webhook subscriptions can have different signing configuration; do not mix secrets.
9. Leave SHOPIFY_ACCESS_TOKEN blank when using Client ID/Client Secret. The backend exchanges these for an access token and refreshes it before expiry. Client-credentials auth requires the store and app to appear in the same Shopify organization.

Sources: https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard and https://shopify.dev/docs/apps/build/authentication-authorization/client-credentials-grant

## Slack

1. Open https://api.slack.com/apps > Create New App > From scratch.
2. Choose a test workspace and name the app CommerceOps AI.
3. OAuth & Permissions > Bot Token Scopes > add chat:write.
4. Install to Workspace. Copy Bot User OAuth Token to SLACK_BOT_TOKEN.
5. Basic Information > App Credentials > Signing Secret > Show. Copy to SLACK_SIGNING_SECRET.
6. Create a dedicated channel, such as commerceops-demo, and invite the bot.
7. Open the channel's details and copy its Channel ID to SLACK_CHANNEL_ID.
8. Open your profile, use the profile menu to Copy member ID, and put it in SLACK_APPROVER_IDS. Additional authorized reviewers are comma separated.
9. After obtaining the HTTPS URL below: Interactivity & Shortcuts > enable Interactivity, use https://YOUR-HOST/webhooks/slack/actions as Request URL and save.

Source: https://docs.slack.dev/app-management/quickstart-app-settings/ and https://docs.slack.dev/authentication/verifying-requests-from-slack/

## HubSpot

1. Sign in to a test HubSpot account with Developer tools access or Super Admin access.
2. Open Settings > Integrations > Service Keys, or Development > Keys > Service Keys.
3. Create a Service Key named CommerceOps AI.
4. Start with the CRM contact read/write permissions used by the v3 engagement APIs: crm.objects.contacts.read and crm.objects.contacts.write. If your account exposes dedicated task read/write permissions, its current picker/API response determines the required grants; we will verify them against the test task endpoint.
5. Create the key, open its details, and Show/Copy the key.
6. Paste only the key into HUBSPOT_ACCESS_TOKEN. Leave HUBSPOT_OWNER_ID blank initially.

New legacy private-app creation has been retired. Existing private-app tokens still work. Service Keys do not provide incoming HubSpot webhooks; this project uses HubSpot outbound task API calls.

Sources: https://developers.hubspot.com/changelog/legacy-private-app-creation-sunset and https://developers.hubspot.com/blog/hubspot-service-keys-the-right-api-credential-for-data-integrations

## Google Sheets

1. Open https://console.cloud.google.com and create/select a project.
2. APIs & Services > Library > Google Sheets API > Enable.
3. IAM & Admin > Service Accounts > Create service account. Name it commerceops-ai. You do not need a broad project Editor role merely to edit an explicitly shared spreadsheet.
4. Open the service account > Keys > Add key > Create new key > JSON > Create.
5. Move the downloaded JSON into the ignored runtime directory, named google-service-account.json. Do not put its contents in .env or GitHub.
6. Set GOOGLE_SERVICE_ACCOUNT_FILE to its full absolute path.
7. Create a Google spreadsheet and rename a worksheet Events.
8. Share that spreadsheet with the service account's client_email as Editor. Keep general access restricted.
9. Copy the spreadsheet ID from the URL portion between /d/ and /edit into GOOGLE_SPREADSHEET_ID.
10. Keep GOOGLE_SHEET_RANGE=Events!A:H. Suggested column headers: event_id, workflow, source, status_at_log_time, created_at, logged_at, mode, error.

Sources: https://developers.google.com/workspace/guides/create-credentials and https://docs.cloud.google.com/iam/docs/keys-create-delete

## Public HTTPS callback URL

The API must be running on port 8000. For a temporary development URL, install cloudflared and run:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```

Keep that terminal running. Save the generated HTTPS URL as PUBLIC_BASE_URL. This makes the local service reachable over the internet; API bearer checks and webhook signatures remain required. Quick Tunnel URLs change on restart and are for testing.

Slack callback: https://YOUR-HOST/webhooks/slack/actions
Shopify callback: https://YOUR-HOST/webhooks/shopify

Do not enable email-gated tunnel access for machine callbacks, since Shopify and Slack cannot complete an interactive email login. The app verifies their signatures.

Source: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

## n8n and GitHub

Local n8n is installed and workflows are exported. No N8N_API_KEY is needed for this local build. Preserve APP_TOKEN. Docker-only POSTGRES_PASSWORD and N8N_ENCRYPTION_KEY are optional unless using Compose. The local n8n demo login is stored in ignored runtime/n8n-local-login.json.

Authenticate GitHub without pasting a PAT here:

```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

Complete the displayed browser/device authorization. The private repository already exists at https://github.com/aaditya599fx/commerceops-ai . Source upload is pending usable GitHub authentication.

## Check saved fields

From the project directory:

```bash
.venv/bin/python scripts/check_connections.py
```

This script makes read-only authentication checks and redacts secrets. It does not create Slack messages, CRM tasks or spreadsheet rows. Tell the assistant when the fields are saved; keep APP_MODE=fixture until live end-to-end verification is arranged.
