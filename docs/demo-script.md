# Demonstration

The recording is a real local browser capture with captions. It labels synthetic fixtures throughout; it does not imply real Shopify, Slack, CRM or Sheets execution.

1. Show n8n's actual Cart recovery canvas and the durable receipt / duplicate / validation branches.
2. Send a fictional cart through the published n8n webhook, then show the same event ID in the control room.
3. Inspect the neutral structured draft and timestamped approval request. The event is waiting; no CRM draft exists yet.
4. Approve with a review reason. Show the CRM/Sheets fixture receipts and audit trail. No email is sent.
5. Replay the exact event. Show the duplicate counter and unchanged action count.
6. Submit a cart without consent. Show `no_marketing_consent`, no model output and no outbound actions.
7. Show inventory/review outputs and the fixed-workload reliability report: explicit denominators, synthetic mode, unmeasured live reliability.

The six real OpenAI calls in `evidence/live-model-smoke.json`, when present, are separate from the fixture UI recording. They measure schema/policy behavior on fictional data and do not prove all integrations.
