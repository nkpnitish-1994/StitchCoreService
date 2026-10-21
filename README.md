# StitchCore

StitchCore is a managed doorstep clothing-alteration platform. `task.md` is the full delivery source of truth; `AGENTS.md` is the durable working context.

## CloudShell build and deploy path

```bash
git clone https://github.com/nkpnitish-1994/StitchCoreService.git
cd StitchCoreService
cp .env.example .env
make bootstrap
make up
make migrate
python scripts/seed_beta.py
make test
```

For the web application:

```bash
cd frontend/web
npm install
npm run build
```

For infrastructure synthesis/deployment (after authenticating the AWS CLI and setting beta/production configuration):

```bash
cd infra/cdk
npm install
npx cdk synth -c env=beta
npx cdk deploy --all -c env=beta
```

Do not deploy production until external provider secrets, domains, database deletion policy, GitHub OIDC roles, and beta integration tests are configured.

## Included

- Role-aware customer, logistics, and admin APIs.
- Customer addresses and multi-garment orders.
- Alteration instructions and measurement JSON per garment.
- Manual, audited status workflow.
- Admin assignment of logistics partners and vendors.
- QR identity for each garment.
- Durable notification-job records and optional SQS publishing.
- Django Admin for early operations.

## Run locally

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

Visit `/admin/` for internal operations, or use `/api/v1/` for the REST endpoints.

## Important endpoints

```text
POST /api/v1/addresses/
GET  /api/v1/addresses/
POST /api/v1/orders/
GET  /api/v1/orders/
GET  /api/v1/orders/{id}/
POST /api/v1/orders/{id}/status/
POST /api/v1/orders/{id}/assign/       (admin only)
POST /api/v1/device-tokens/
```

## Notification path

Set `NOTIFICATION_QUEUE_URL` to an SQS queue URL in AWS. Each approved order status
change creates a `NotificationJob` in PostgreSQL and publishes the minimum delivery
payload plus its ID to SQS. An SQS-triggered Lambda owns provider delivery and retries. The Lambda adapter is a
deliberate integration boundary: it needs the selected WhatsApp provider and FCM
credentials before real messages can be sent.

## Production configuration

Set `DEBUG=false`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `DB_ENGINE`, `DB_NAME`,
`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `AWS_REGION`, `NOTIFICATION_QUEUE_URL`, and
`INTERNAL_NOTIFICATION_SECRET`. Use `DB_ENGINE=django.db.backends.postgresql` for
RDS PostgreSQL; SQLite is only for local development.

## API contract

Run `make openapi` to regenerate and validate `packages/contracts/openapi.yaml`.
The live schema is available at `/api/schema/` and Swagger UI at `/api/docs/`.
Business endpoints use `/api/v1/`; unversioned business routes are not supported.
Errors use `{"code": "...", "message": "...", "fields": {}}`; validation errors
include field details. Keep the generated contract committed with API changes.
