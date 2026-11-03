# Measured synthetic evaluation

Run: 2026-11-03T05:30:22.377206+00:00

single-process local Python, SQLite, deterministic fixture providers

161 fictional events across six workflows; 30 duplicate deliveries replayed; no external service calls. Eligible excludes policy-blocked/rejected; pending and failed eligible events remain in denominator.

| Measurement | Result |
|---|---|
| Unique events | 161 |
| Successful / eligible | 152 / 152 |
| Safely blocked | 9 |
| Duplicate deliveries suppressed | 30 |
| Duplicate recorded effect keys | 0 |
| Fixture schema-valid outputs | 152 / 152 |

These results measure a deterministic local workload. They are not evidence of live integration reliability, model quality, production throughput or business improvement.

Fault injection and webhook authentication are covered separately by tests/test_system.py. Raw pytest output is in evidence/pytest.txt.

Not measured: Live API reliability, LLM classification accuracy, Human approval latency, Business impact, Time savings, Dollar cost, Production throughput, Exactly-once delivery at third parties.
