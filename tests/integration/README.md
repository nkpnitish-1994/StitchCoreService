# Integration test harness

Run against local Docker services or beta only. Never point this suite at production.

Required cases: customer order/quote, role authorization, pickup confirmation, payment-webhook idempotency, media authorization, and notification retry.

Set `TEST_API_BASE_URL` and role tokens, then run the package chosen by the team (pytest is recommended). Keep provider tests mocked locally and use sandbox credentials in beta.

