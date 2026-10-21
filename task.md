# StitchCore — Delivery Plan and Source of Truth

> **Purpose:** This document is the execution plan for building StitchCore. Read it before making architectural, product, or infrastructure changes. Update it when a material decision, scope boundary, or milestone changes.

## 1. Product mission

StitchCore is an on-demand, managed clothing-alteration service. A customer submits garments that do not fit, states the required alteration and relevant measurements, selects a pickup window, and receives the altered garments back. StitchCore coordinates pickup, vendor handover, alteration completion, return collection, and delivery.

The initial product succeeds when a customer can place an order in a few minutes and the operations team can reliably maintain custody, complete an alteration, and return every garment on time.

### MVP operating model

- Launch in one small, dense service area only.
- Use one trusted alteration vendor and one or two logistics partners.
- Batch collection in the evening, hand garments to the vendor, then collect and deliver completed garments the following day.
- Keep routing, vendor allocation, quality checks, and exception decisions manual.
- Offer a limited catalogue of predictable, standard alterations first.
- Use a fixed price catalogue whenever possible. Send exceptions to admin/customer approval before work begins.

### Initial service catalogue

| Garment | Supported initial services |
|---|---|
| Trousers | Hem/length, waist in/out, taper, seat adjustment |
| Shirt | Sleeve length, side fitting, shirt length |
| Kurta | Sleeve length, side fitting, hem/length |
| Dress/skirt | Hem/length, basic side fitting |

Not initially supported: expensive wedding garments, leather, major redesigns, complicated embroidery work, or unpriced custom work.

## 2. Goals, success metrics, and constraints

### Product goals

1. Make order placement feel premium, simple, and trustworthy.
2. Make each garment traceable from pickup through return delivery.
3. Give operations staff the minimum tools needed to run the service manually without spreadsheets becoming the system of record.
4. Keep the technical system inexpensive and operationally simple for a one-city pilot.

### Pilot success metrics

| Metric | Initial target |
|---|---|
| Customer order completion | ≥ 70% after entering the order flow |
| Pickup success rate | ≥ 90% on first attempt |
| On-time delivery | ≥ 90% against promised date |
| Garment custody incidents | 0 |
| Rework rate | Track from day one; use findings to improve measurement flow |
| Status-notification delivery | ≥ 95% successful or retryable |
| Average turnaround | Define per service area; initially 24–48 hours |

### Non-negotiable constraints

- PostgreSQL is the permanent source of truth for all business data.
- No order status change may be silently overwritten; every change needs an immutable audit event.
- A logistics partner can only access orders assigned to that partner.
- Customer address and phone data are visible only to customer, admin, and the assigned logistics partner.
- All monetary values are stored in **paise** as integers; never use float/decimal rupees in API business logic.
- Images are stored privately; clients receive signed URLs rather than public storage URLs.
- No secrets, AWS credentials, payment credentials, or provider tokens are committed to Git.

## 3. Roles and permissions

### Customer

- Sign in by phone OTP.
- Manage own profile and saved addresses.
- Create an order, submit garments, select alteration services, attach measurements/photos, select pickup slot, and pay.
- View only own orders, garments, receipts, notifications, and rework requests.
- Track order timeline and receive delivery updates.

### Admin / operations

- See all orders, customers, garments, vendors, logistics assignments, payments, status events, notifications, and exceptions.
- Assign/reassign logistics partner and vendor manually.
- Update any valid status and resolve exceptions.
- Configure catalogue, pricing, service areas, pickup slots, vendors, and partner accounts.
- Approve price changes, refunds, cancellation, and rework decisions.
- Review delayed orders and notification failures.

### Logistics partner

- See only their assigned tasks and the minimum customer information required to execute them.
- Open navigation/call links for assigned pickups and deliveries.
- Confirm garment count, scan/enter garment QR ID, capture condition/proof photos, and record notes.
- Mark allowed task/status transitions only.
- Cannot change prices, vendor, customer, payment, or other partner assignments.

### Vendor

Vendor capability is intentionally minimal in the first release.

- Vendor may eventually have a web profile to see only orders assigned to that vendor.
- Vendor may mark alteration work complete and add notes/photos, subject to admin review.
- Until that interface is proven necessary, vendor work is coordinated by admin/logistics through secure job links or WhatsApp.

## 4. Customer and operations workflows

### 4.1 Customer order journey

1. Customer signs in using phone OTP.
2. Customer selects or creates pickup/delivery address.
3. Customer adds one or more garments.
4. For each garment, customer selects a supported alteration service.
5. Customer supplies one of the measurement methods described in section 5.
6. Customer adds optional notes and reference photos.
7. System displays transparent service price, pickup fee, pickup slot, and estimated return date.
8. Customer reviews order and pays using Razorpay.
9. System confirms the order and shows a trackable order number.
10. Customer receives status updates until delivery is complete.

### 4.2 Manual operational lifecycle

```text
Customer order
  → Admin assigns logistics partner and vendor
  → Logistics partner picks up garments and records proof
  → Logistics/admin confirms vendor handover
  → Vendor completes alteration
  → Admin/logistics marks completion/readiness
  → Logistics partner collects completed garments
  → Logistics partner delivers and records proof
```

### 4.3 Status state machine

```text
placed
  → pickup_assigned
  → picked_up
  → at_vendor
  → alteration_complete
  → ready_for_delivery
  → out_for_delivery
  → delivered
```

Exception paths:

```text
pickup_assigned → pickup_failed → pickup_assigned | cancelled
at_vendor → customer_approval_needed → at_vendor | cancelled
at_vendor | delivered → rework_required → at_vendor | alteration_complete
placed | pickup_assigned → cancelled
```

Each transition must write:

- `from_status` and `to_status`
- authenticated actor
- timestamp
- optional note
- optional proof photo/document reference

### 4.4 Garment custody rules

- Generate a customer-facing `ORD-YYYYMMDD-XXXXXX` order number.
- Generate a unique `GRM-XXXXXXXX` QR-friendly identifier for every garment line item.
- Require pickup confirmation before `picked_up`.
- Require vendor handover acknowledgement before `at_vendor`.
- Require delivery OTP or proof photo/signature before `delivered`.
- Preserve condition notes and evidence to resolve loss/damage disputes.

## 5. Measurement framework

The measurement experience must be structured but low-friction. Do not require a full body-measurement form by default.

### 5.1 Measurement modes

| Mode | Customer action | Best use |
|---|---|---|
| Direct alteration delta | “Shorten by 2 inches” or “reduce waist by 1 inch” | Standard/low-risk alterations |
| Final garment measurement | “Finished waist should be 32 inches” | Customers who know garment measurements |
| Reference garment | Add photo/details of a well-fitting garment | Fit matching where direct dimensions are unclear |
| Pickup measurement | Select “measure at pickup” | Customer does not know required measurements |
| Tailor recommendation | Customer gives a goal; admin/vendor seeks approval | Exceptional/custom work only |

### 5.2 Structured measurement schema

Each `AlterationItem` must store a versioned structured JSON payload rather than free text only.

```json
{
  "schema_version": 1,
  "measurement_mode": "alteration_delta",
  "unit": "in",
  "values": {
    "waist_reduce_by": 1
  },
  "reference_garment": null,
  "customer_confirmation": true
}
```

Use service-specific validation rules. Examples:

```text
trousers.reduce_waist:
  required: waist_reduce_by OR target_waist OR pickup_measurement
  valid unit: in | cm
  allowed range: configured safe range

shirt.shorten_sleeve:
  required: shorten_by OR target_sleeve_length OR pickup_measurement
```

### 5.3 Measurement product requirements

- Display diagrams and plain-language guidance for each measurement when a user needs to enter it.
- Use inches and centimetres; store both original input and normalized value where useful.
- Show a human-readable final instruction before payment.
- Require customer confirmation for any admin/vendor price or measurement change.
- Keep a saved measurement profile optional, encrypted/permissioned, and editable by the customer.
- Record who captured a pickup measurement and when.
- Do not add AI sizing or photo-based automated measurement to the MVP.

## 6. Product surfaces

### 6.1 Customer website

Implement a mobile-first Next.js web application. It must work excellently in a mobile browser before native applications are released.

Required screens:

- Landing/service-area check
- Phone OTP sign-in/sign-up
- Service catalogue and pricing
- Saved addresses
- New order wizard
- Garment/alteration/measurement details
- Photo upload
- Pickup slot selection
- Checkout and Razorpay payment
- Order confirmation
- Order history and order detail/timeline
- Saved measurements
- Help/support and rework request

### 6.2 Customer mobile apps

Build a shared React Native + Expo app for Android and iOS after the core web flow/API is stable.

Required capability:

- Same customer flows as website.
- Push-notification permission and FCM device registration.
- Camera/photo uploads.
- Deep links from WhatsApp/push into order details.
- Secure storage for session token.

### 6.3 Admin web dashboard

Start with Django Admin for operational validation. Build a dedicated Next.js admin dashboard when workflows stabilize.

Required dashboard capabilities:

- Order board searchable by order number, customer phone, status, date, vendor, and logistics partner.
- Order detail: garments, instructions, photos, QR IDs, payment, address, full audit timeline, and notifications.
- Manual assignment to logistics partner and vendor.
- Exception queues: pickup failed, approval needed, overdue, rework, failed notification, refund/cancellation.
- Service catalogue and price management.
- Vendor and logistics partner management.
- Daily operations list with filtering/export; **not** automatic route optimization.
- Basic operational reporting: order volume, turnaround, cancellation, rework, and delivery failures.

### 6.4 Logistics mobile mode

Implement as a role-specific area of the same React Native application, not a separate backend or codebase.

Required screens:

- Today’s assigned tasks grouped as pickup/delivery/vendor handover.
- Task detail with customer name, masked/unmasked contact according to assignment, address, map link, notes, garments, and expected action.
- QR scanner/manual code entry.
- Pickup confirmation: count, photo, condition note.
- Vendor handover / collection confirmation.
- Delivery confirmation: delivery OTP and/or proof photo.
- Failure reason and reschedule request.
- Offline-friendly drafts for proof capture; upload/reconcile when connection returns.

### 6.5 Vendor web profile (phase after manual pilot)

Required only after vendor workflow is validated:

- Vendor login and own assigned-job list.
- Garment/alteration instructions, photos, and due date.
- Mark “alteration complete” with notes.
- No access to unrelated customer data/orders.
- Admin retains final control of fulfillment status.

## 7. Backend core service

### 7.1 Technology and repository direction

- Language/framework: Python, Django, Django REST Framework.
- Database: PostgreSQL locally via Docker where possible; Amazon RDS PostgreSQL in AWS.
- API style: versioned JSON REST API, starting at `/api/v1/`.
- Authentication: secure phone OTP plus short-lived access token/refresh-token flow.
- API contract: generate and publish OpenAPI schema; clients use generated/shared typed contracts where practical.
- Background work: **SQS plus Lambda only** for notification delivery. Do not add Redis or Celery to MVP.

Suggested repository layout after the application grows:

```text
StitchCoreService/
  backend/                 Django project and domain apps
  frontend/web/            Next.js customer/admin/vendor web application
  frontend/mobile/         React Native / Expo app
  packages/contracts/      OpenAPI-generated or shared API types
  infra/cdk/               AWS CDK application
  tests/integration/       Black-box API/infrastructure tests
  docs/                    ADRs, runbooks, API/integration docs
  task.md                  This source of truth
  AGENTS.md                Durable agent/developer working rules
```

### 7.2 Domain modules

| Module | Responsibility |
|---|---|
| `accounts` | User, role, phone OTP, sessions, device tokens, consent |
| `catalog` | Garment types, alteration services, measurement schemas, pricing, serviceability |
| `orders` | Cart/order, garments, alterations, totals, lifecycle/state machine, audit events |
| `fulfillment` | Logistics assignment, vendor assignment, pickup/delivery proofs, exception tasks |
| `payments` | Razorpay order creation, webhook verification, refunds, payment ledger |
| `media` | S3 signed upload/download URLs, metadata, virus/type/size validation |
| `notifications` | Notification jobs, SQS publishing, provider callback, delivery audit |
| `support` | Rework, cancellation, customer approvals, notes |
| `reporting` | Read-only operational summaries and exports |

### 7.3 Core data model

Implement/extend these entities with migrations and constraints:

| Entity | Key fields/relationships |
|---|---|
| User | id, phone, name, role, active, consent metadata |
| Address | user, label, address fields, geo coordinates, serviceability state |
| Vendor | name, contacts, service area, active, supported services |
| LogisticsPartner | user/profile, active, service area, internal notes |
| Service | code, garment type, name, measurement schema/version, base price, active |
| ServicePrice | service, market/service area, effective period, price paise |
| Order | public number, customer, address snapshot, status, pickup slot, expected return, totals, payment state |
| Garment | order, type, QR ID, color/brand, condition notes, custody/photo metadata |
| AlterationItem | garment, service, measurement payload/version, customer notes, quoted/approved price |
| Assignment | order, logistics partner, vendor, assigned by, timestamps |
| StatusEvent | order, from/to status, actor, timestamp, note, proof reference |
| MediaAsset | owner/entity link, S3 key, media type, checksum, uploader, upload status |
| Payment | order, Razorpay IDs, amount paise, state, webhook payload reference, refund state |
| NotificationJob | order, channel, template, recipient, payload, status, provider ID, retry/error state |
| CustomerApproval | order, requested change, before/after values, expiry, decision, approver |
| ReworkRequest | order/garment, reason, evidence, decision, resolution |

### 7.4 API requirements

#### Customer APIs

```text
POST   /api/v1/auth/otp/request
POST   /api/v1/auth/otp/verify
POST   /api/v1/auth/refresh
GET    /api/v1/me

GET    /api/v1/addresses
POST   /api/v1/addresses
PATCH  /api/v1/addresses/{id}

GET    /api/v1/catalog/services
GET    /api/v1/catalog/serviceability
POST   /api/v1/orders/quote
POST   /api/v1/orders
GET    /api/v1/orders
GET    /api/v1/orders/{id}
POST   /api/v1/orders/{id}/cancel-request
POST   /api/v1/orders/{id}/rework-request

POST   /api/v1/media/upload-url
POST   /api/v1/payments/create-order
POST   /api/v1/devices
```

#### Operations APIs

```text
GET    /api/v1/admin/orders
POST   /api/v1/admin/orders/{id}/assign
POST   /api/v1/admin/orders/{id}/status
POST   /api/v1/admin/orders/{id}/approve-change
GET    /api/v1/admin/exceptions
CRUD   /api/v1/admin/catalog/services
CRUD   /api/v1/admin/catalog/prices
CRUD   /api/v1/admin/vendors
CRUD   /api/v1/admin/logistics-partners
```

#### Logistics APIs

```text
GET    /api/v1/logistics/tasks?date=YYYY-MM-DD
GET    /api/v1/logistics/tasks/{id}
POST   /api/v1/logistics/orders/{id}/pickup-confirmation
POST   /api/v1/logistics/orders/{id}/vendor-handover
POST   /api/v1/logistics/orders/{id}/vendor-collection
POST   /api/v1/logistics/orders/{id}/delivery-confirmation
POST   /api/v1/logistics/orders/{id}/failure
```

#### Webhooks/internal APIs

```text
POST /api/v1/webhooks/razorpay
POST /api/v1/internal/notifications/{job_id}/delivery
```

All webhook handlers must verify the provider signature, be idempotent, and write an audit record.

### 7.5 Backend functional acceptance criteria

- A customer cannot submit an order using another customer’s address.
- An order total is calculated only on the server from active catalogue pricing.
- Every garment has a unique ID before pickup.
- Invalid or unauthorized state transitions fail without changing database state.
- A logistics partner cannot retrieve or update an unassigned order.
- Assigning a partner/vendor and changing status appear in the audit timeline.
- Payment webhooks are safe to replay.
- Notification failure never rolls back a successful order/status transaction.
- API validation errors are structured and suitable for client rendering.

## 8. Notifications and external integrations

### 8.1 Notification policy

| Event | Customer | Logistics | Admin |
|---|---|---|---|
| Order placed/payment confirmed | Push + WhatsApp | — | Dashboard |
| Pickup assigned | Optional | Push + WhatsApp task link | Dashboard |
| Picked up | Push + WhatsApp | — | Dashboard |
| Approval needed | Push + WhatsApp | — | Dashboard/alert |
| Ready/out for delivery | Push + WhatsApp | Push/task | Dashboard |
| Delivered | Push + WhatsApp | — | Dashboard |
| Failed operation | Appropriate alert | Task update | Dashboard/alert |

### 8.2 Integration design

- **Razorpay:** server creates payment order; web/mobile completes checkout; Razorpay webhook is authoritative for payment result.
- **WhatsApp:** choose a BSP before implementation; use approved templates and secure task links. Do not transmit the full address in message text.
- **FCM:** register device tokens per user/device/platform; deep-link notification to the relevant order/task.
- **SMS:** OTP and high-priority fallback only.
- **S3:** client requests presigned upload URL; server validates attachment metadata; media persists as private object.
- **SQS/Lambda:** Django creates persistent notification job then publishes a minimal payload after DB commit. Lambda sends provider request, retries via SQS, and records final result using protected internal API.

## 9. AWS CDK infrastructure package

### 9.1 CDK principles

- Use AWS CDK v2 with TypeScript.
- Keep all infrastructure under `infra/cdk/`.
- Use separate AWS accounts for beta and production if possible; at minimum use separate stacks, databases, buckets, queues, and secrets.
- Default target region: `ap-south-1` (Mumbai).
- All infrastructure changes are reviewed through pull requests and deployed through CI/CD; avoid console-created production resources.
- Tag all resources with `Project=StitchCore`, `Environment`, `Owner`, and `CostCenter`.

### 9.2 Environments

| Environment | Purpose | Data | Public access |
|---|---|---|---|
| Local | Developer tests | Local/sample data | Local only |
| Beta | Internal/pilot validation | Synthetic + approved beta customer data | Restricted real domain |
| Production | Live customers | Real data | Live domain only |

### 9.3 CDK stacks

```text
FoundationStack
  - VPC/subnets/security groups (keep initial networking simple)
  - Route 53 hosted-zone references / ACM certificates
  - KMS keys where appropriate
  - CloudWatch log groups / retention policies

DataStack
  - RDS PostgreSQL instance/cluster, subnet/security group, backups
  - S3 private media bucket, encryption, lifecycle rules, CORS
  - Secrets Manager database credentials and application secrets

ComputeStack
  - ECR repositories for backend and web images
  - ECS cluster, Fargate task definition/service for Django API
  - Application Load Balancer, HTTPS listener, health checks
  - ECS task roles with least privilege
  - Lambda function for notifications

MessagingStack
  - SQS notification queue
  - Dead-letter queue and alarm
  - SQS-to-Lambda event source mapping

EdgeStack
  - CloudFront/S3 or ECS hosting design for web app
  - DNS records and TLS

ObservabilityStack
  - CloudWatch dashboards
  - Alarms: API 5xx, ECS task failure, Lambda failure/throttle, SQS backlog/DLQ, RDS capacity
  - Alert notification topic/integration
```

### 9.4 Network/cost approach

- Begin with one API Fargate task at 0.5 vCPU / 1 GB and scale after load evidence.
- Use a private RDS instance inaccessible from the public internet.
- Do not introduce a NAT Gateway by default; assess the egress design deliberately because it can materially raise MVP cost.
- Use VPC endpoints or an approved simplified network design only after security/cost review.
- Use S3 lifecycle policies for media retention and deletion policy.
- Configure database backups, restore testing, and deletion protection for production.

### 9.5 CDK acceptance criteria

- `cdk synth` succeeds in CI for beta and production configurations.
- `cdk diff` is reviewed before any production change.
- Each stack deploys cleanly into a new beta account/namespace.
- ECS task can read only needed secrets and write only permitted S3/SQS/log resources.
- API health endpoint is reachable only through the expected load balancer/domain route.
- SQS failure routes to a DLQ and produces an alarm.
- Destructive resource deletion is blocked or requires explicit break-glass approval in production.

## 10. CI/CD and release process

### 10.1 Branching strategy

```text
main                protected; always deployable
feature/*           short-lived development branches
release/*           optional stabilization branches only if needed
```

Every feature reaches `main` through a pull request with required checks. Do not commit directly to protected `main` after initial bootstrap.

### 10.2 Pipeline stages

```mermaid
flowchart LR
  PR["Pull request"] --> CHECKS["Lint · type-check · unit tests · security scan"]
  CHECKS --> PREVIEW["Build images · CDK synth/diff"]
  PREVIEW --> MERGE["Merge to main"]
  MERGE --> BETA["Deploy beta"]
  BETA --> INTEGRATION["Run integration + smoke tests"]
  INTEGRATION --> APPROVAL["Manual production approval"]
  APPROVAL --> PROD["Deploy production"]
  PROD --> SMOKE["Production smoke test + monitoring"]
```

### 10.3 Pull request pipeline

Run on every pull request:

- Format/lint Python, TypeScript, YAML, Dockerfiles, and CDK code.
- Run Python type checks and frontend type checks.
- Run backend unit tests and migration consistency checks.
- Run frontend unit/component tests.
- Build Docker images without pushing production tags.
- Run dependency and secret scanning.
- Run `cdk synth` for beta and production configurations.
- Publish a `cdk diff` summary for infrastructure changes.
- Optionally deploy a temporary preview environment only after cost/security review.

### 10.4 Beta deployment pipeline

Trigger: merge to `main`.

1. Build immutable backend/web container artifacts tagged with commit SHA.
2. Push images to ECR.
3. Deploy CDK beta stacks.
4. Run database migrations as a one-off ECS task using a locked, idempotent migration job.
5. Update ECS service using rolling or blue/green deployment.
6. Wait for ALB/ECS health checks.
7. Run integration suite against beta.
8. Publish deployment result, revision, migration version, and test report.

Beta must use its own RDS database, S3 prefix/bucket, SQS queues, and provider sandbox/test credentials where available.

### 10.5 Production deployment pipeline

Trigger: explicit manual approval of a beta-validated commit/tag.

1. Verify the same immutable artifact SHA passed beta integration tests.
2. Require human approval by an authorized maintainer.
3. Take/verify database backup and migration rollback plan.
4. Deploy production CDK changes.
5. Run production-safe database migrations.
6. Deploy ECS application with health checks and rollback on failure.
7. Run non-destructive production smoke tests.
8. Monitor alarms/error rate for a defined window.
9. Record deployment metadata and notify the team.

Never run seeded test data, destructive cleanup, or real WhatsApp/SMS notification tests against production.

### 10.6 Deployment safety

- Use GitHub Actions with AWS OIDC federation; do not store long-lived AWS access keys in GitHub secrets.
- Store third-party credentials in AWS Secrets Manager and inject only at runtime.
- Require environment protection rules for production.
- Version database migrations and make them backwards-compatible where rolling deployments overlap versions.
- Keep a documented rollback procedure: application rollback, feature flag disablement, database forward-fix strategy.

## 11. Testing strategy

### 11.1 Test layers

| Layer | Scope | Runs when |
|---|---|---|
| Unit tests | Domain services, serializers, permissions, pricing, state machine | Every PR |
| API tests | REST request/response, auth, validation, object-level authorization | Every PR |
| Database tests | Migrations, constraints, transaction/idempotency behavior | Every PR and beta |
| Frontend component tests | Forms, measurement input, status presentation, role gating | Every PR |
| End-to-end tests | Customer, admin, logistics browser/mobile-critical workflows | Beta deployment |
| Integration tests | Razorpay/WhatsApp/FCM/SQS/Lambda adapters using test/sandbox modes | Beta deployment |
| Infrastructure tests | CDK assertions, synth/diff, deploy smoke validation | Every PR/beta |
| Security tests | Dependency/secret scan, permission tests, auth abuse cases | Every PR + scheduled |
| Performance checks | Quote/order/status API baseline under expected pilot load | Before launch and release milestones |

### 11.2 Mandatory backend scenarios

- Customer OTP request/verify throttling and invalid-code handling.
- Customer can create an order only with own serviceable address.
- Unsupported garment/service/measurement combinations are rejected.
- Server calculates price independently of client-provided totals.
- One order supports multiple garments and multiple alterations.
- Each valid state transition creates one immutable `StatusEvent`.
- Every forbidden transition is rejected.
- Logistics partner cannot access another partner’s order.
- Admin can assign/reassign partner/vendor and action appears in audit data.
- Payment webhook signature validation, idempotency, duplicate delivery, and refund state.
- S3 signed uploads reject unsupported file type/oversize requests.
- Notification job persists even if SQS publish/provider delivery fails.
- Lambda retry and DLQ behavior are tested with simulated provider failure.

### 11.3 Mandatory end-to-end beta scenarios

1. Customer signs in, creates address, chooses trousers waist alteration, supplies measurement, pays in Razorpay test mode, and sees confirmed order.
2. Admin assigns logistics partner and vendor.
3. Logistics partner sees only assigned task, records QR/proof, and marks pickup.
4. Customer receives simulated or sandboxed notification and sees timeline update.
5. Admin/logistics completes vendor and delivery statuses.
6. Logistics partner completes delivery with proof/OTP.
7. Customer sees delivered order and may open a rework request.
8. Admin handles a failed pickup and reschedules it.
9. Approval-needed flow prevents alteration completion until customer/admin approval.
10. Unauthorized customer/logistics user receives `403`/`404` and no sensitive information.

### 11.4 Test data and environments

- Use factories/fixtures, not production database snapshots, in CI.
- Test phone numbers, Razorpay sandbox credentials, and provider sandbox/mock adapters are mandatory for beta.
- Mask/redact phone numbers, addresses, tokens, and payment data in logs and test reports.
- Seed beta test users for each role and make reset scripts safe/idempotent.

## 12. Implementation roadmap

### Phase 0 — Foundation (complete/partially complete)

- [x] Establish Django/DRF repository foundation.
- [x] Implement initial domain models for users, address, vendor, order, garment, alterations, status events, device tokens, and notification jobs.
- [x] Implement early order creation, assignment, status workflow, Django Admin, SQS publisher skeleton, Lambda skeleton, and basic test.
- [x] Create `AGENTS.md` and this implementation plan.
- [x] Move API routes to `/api/v1/` and generate OpenAPI contract. Verified versioned routes, standardized errors, corrected action schemas, Lambda callback URL, and committed-schema consistency with 11 backend tests; OpenAPI validates without warnings.
- [ ] Add local Docker Compose for Django, PostgreSQL, and test services.
- [ ] Add environment configuration template and contributor setup instructions.

### Phase 1 — Backend pilot readiness

- [ ] Phone OTP authentication and token lifecycle.
- [ ] Full catalogue, pricing, serviceability, pickup-slot, and quote engine.
- [ ] Production-ready order lifecycle and assignment history.
- [ ] Media uploads with S3 presigned URLs and proof metadata.
- [ ] Razorpay payment order, webhook verification, payment states/refunds.
- [ ] Customer approvals, cancellation, rework domains.
- [ ] Notification service interfaces and provider adapters/mocks.
- [ ] Complete authorization, audit, validation, and unit/API test coverage.

### Phase 2 — Customer web pilot

- [ ] Next.js project and design system.
- [ ] OTP, address, catalogue, order wizard, measurement framework, uploads.
- [ ] Razorpay checkout.
- [ ] Order tracking/history, support/rework.
- [ ] Responsive/mobile browser QA and accessibility baseline.

### Phase 3 — Operations and logistics

- [ ] Polish Django Admin views/actions for first operational pilot.
- [ ] Admin web dashboard order queue, assignment, exceptions, catalogue management.
- [ ] React Native/Expo app shell with customer and logistics roles.
- [ ] Logistics task workflow, QR scanning, photo proof, offline draft/retry support.
- [ ] Push notification device registration/deep links.
- [ ] Vendor profile only if manual pilot proves the need.

### Phase 4 — Infrastructure and deployments

- [ ] Scaffold TypeScript AWS CDK application and stack boundaries.
- [ ] Provision beta environment.
- [ ] Container build/ECR/ECS Fargate deployment.
- [ ] RDS/S3/SQS/Lambda/Secrets/monitoring setup.
- [ ] GitHub Actions PR checks and beta deployment.
- [ ] Production environment, approval gate, deployment/rollback runbooks.

### Phase 5 — Pilot launch hardening

- [ ] End-to-end beta suite covers all mandatory scenarios.
- [ ] Performance baseline and security review.
- [ ] Data privacy, support, incident, rework, and lost-garment runbooks.
- [ ] Staff training and dry-run pickup/vendor/delivery day.
- [ ] Controlled customer beta launch in one locality.

## 13. Definition of done

A feature is done only when:

- Product behavior matches this plan and has explicit acceptance criteria.
- Backend authorization and validation are enforced server-side.
- Unit/API tests cover normal and failure paths.
- UI handles loading, empty, validation-error, and retry states.
- Relevant audit events and notifications are emitted.
- Infrastructure changes are represented in CDK, not undocumented console changes.
- CI is green, beta is deployed/tested when applicable, and docs are updated.
- No secrets, personal data, or provider credentials are in source control or test logs.

## 14. Explicit MVP exclusions

- Automatic route optimization or live driver GPS tracking.
- Automatic vendor allocation.
- Automatic quality checks.
- Complex AI/photo measurement extraction.
- Dynamic surge pricing.
- Full vendor marketplace/multi-vendor bidding.
- Multi-city fulfillment automation.
- Redis/Celery task infrastructure.

## 15. Decisions requiring owner input before implementation

These do not block local backend work, but they block production integration:

1. Launch city/localities and serviceable pincodes.
2. Final standard service catalogue and price list.
3. Pickup/delivery fee and free-delivery threshold.
4. Turnaround promise by service type.
5. Rework, cancellation, loss/damage, and refund policy.
6. WhatsApp provider/BSP selection.
7. SMS provider selection.
8. OTP approach/vendor.
9. Razorpay merchant account and webhook configuration.
10. Customer-facing brand, domain, and design direction.
11. Beta/production AWS account separation and deployment approvers.

## 16. Low-level execution blueprint for new development sessions

This section is intentionally prescriptive. A new Codex session should use it as the implementation handoff and should not invent a different architecture without recording an ADR and requesting approval.

### 16.1 First actions for a new coding session

Run these commands from the repository root before changing code:

```bash
pwd
git status --short --branch
git log --oneline -5
sed -n '1,240p' AGENTS.md
sed -n '1,260p' task.md
find . -maxdepth 3 -type f -not -path './.venv/*' | sort
```

Then:

1. Identify the first unchecked item in the active roadmap phase.
2. Confirm no existing user changes overlap it; preserve unrelated changes.
3. Implement only one cohesive vertical slice at a time.
4. Add/adjust migrations, unit tests, API tests, documentation, and environment configuration in the same change.
5. Run the required verification commands before committing.
6. Update the matching checkbox in this file only after the feature is genuinely verified.

Do not try to build all roles, clients, providers, and infrastructure in one change.

### 16.2 Current repository baseline

The existing root-level Django project is an early foundation. It currently contains `config/`, `operations/`, `infra/lambda/notifications/`, `Dockerfile`, and requirements files. It uses SQLite locally and has an initial custom user/order workflow.

Treat the current implementation as a scaffold, not a finished API contract. Preserve valid work, but refactor it into the target layout below incrementally. Do not break existing migrations or silently change identifiers/status values.

### 16.3 Target repository structure

Move to this structure through small compatible changes; do not perform a destructive mass move during feature work.

```text
.
├── AGENTS.md
├── task.md
├── README.md
├── .env.example
├── compose.yaml
├── Makefile
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py
│   │   │   ├── beta.py
│   │   │   └── production.py
│   │   ├── urls.py
│   │   └── celery.py                  # Do not create for MVP
│   ├── apps/
│   │   ├── accounts/
│   │   ├── catalog/
│   │   ├── orders/
│   │   ├── fulfillment/
│   │   ├── payments/
│   │   ├── media/
│   │   ├── notifications/
│   │   └── support/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── web/                           # Next.js app
│   └── mobile/                        # Expo / React Native app
├── packages/
│   └── contracts/                     # OpenAPI schema + generated TS client
├── infra/
│   ├── cdk/
│   └── lambda/notifications/
├── scripts/
│   ├── seed_beta.py
│   └── wait_for_http.py
├── tests/
│   └── integration/
└── .github/workflows/
```

The migration from the current root-level Django project can be deferred until the core API is stable. If deferring it, retain the same domain boundaries in code modules.

### 16.4 Local development environment

#### Required developer tools

```text
Python 3.12+ (pin a tested version in CI)
Node.js 22+ and pnpm
Docker Desktop / Docker Engine
AWS CLI v2
AWS CDK v2
GitHub CLI (optional, for PRs)
```

#### Required local services

| Service | Local implementation | Production implementation |
|---|---|---|
| Database | PostgreSQL container | RDS PostgreSQL |
| Object storage | MinIO or mocked S3 client | S3 |
| Queue | LocalStack SQS or mocked publisher | SQS |
| Notifications | Fake adapter / request recorder | Lambda + provider APIs |
| Payment | Razorpay test mode/mock gateway | Razorpay live mode |

#### `.env.example` contract

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.local
DJANGO_SECRET_KEY=replace-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DATABASE_URL=postgresql://stitchcore:stitchcore@localhost:5432/stitchcore
REDIS_URL=                         # intentionally unused by MVP

AWS_REGION=ap-south-1
AWS_S3_MEDIA_BUCKET=stitchcore-local-media
AWS_SQS_NOTIFICATION_QUEUE_URL=
AWS_ENDPOINT_URL=                  # LocalStack only; blank in AWS

INTERNAL_NOTIFICATION_SECRET=replace-me
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
WHATSAPP_PROVIDER=
WHATSAPP_API_BASE_URL=
WHATSAPP_ACCESS_TOKEN=
FCM_SERVICE_ACCOUNT_JSON=
SMS_PROVIDER=
OTP_SECRET=replace-me
```

Never add real values to `.env.example`, checked-in files, test snapshots, or GitHub Actions logs.

#### Standard commands to add to `Makefile`

```make
bootstrap:          ## Install Python/Node dependencies
up:                 ## Start PostgreSQL and local dependencies
down:               ## Stop local dependencies
migrate:            ## Apply Django migrations
makemigrations:     ## Create Django migrations
seed-beta:          ## Create deterministic beta users/catalog/orders
test:               ## Run all backend unit/API tests
test-integration:   ## Run black-box integration suite
lint:               ## Run Python/TS lint and formatting checks
typecheck:          ## Run Python and TS type checks
openapi:            ## Generate/validate OpenAPI schema and TS client
cdk-synth:          ## Synthesize selected CDK environment
```

### 16.5 Backend coding rules

#### Layering

```text
HTTP view/controller
  → serializer/request DTO validation
  → domain service function
  → Django ORM transaction
  → domain event / notification job
  → external publisher/adapter after transaction commit
```

- Views must not contain pricing rules, authorization policy beyond invoking permissions, or state-machine logic.
- Serializers validate input shape and simple field constraints; domain services validate business invariants.
- Domain services must be individually unit-testable.
- Use `transaction.atomic()` for multi-record operations.
- Use `transaction.on_commit()` before publishing SQS work. Never publish while a transaction may still roll back.
- Adapters for Razorpay, S3, WhatsApp, FCM, SMS, SQS, and Lambda callbacks must be behind interfaces that can be faked in tests.

#### Error response contract

Use one predictable error shape:

```json
{
  "code": "invalid_status_transition",
  "message": "This order cannot be moved from picked_up to delivered.",
  "fields": {}
}
```

Validation errors may include `fields` keyed by input field. Do not return framework tracebacks or provider responses to clients.

#### ID and timestamp policy

- Internal primary keys: UUID.
- Customer order number: immutable human-readable string, for example `ORD-20261021-A1B2C3`.
- Garment code: immutable unique string, for example `GRM-8F2K9Q`.
- Store timestamps in UTC; display in `Asia/Kolkata` in Indian customer/operations interfaces.
- Use soft cancellation/status rather than deleting orders, payments, or status events.

### 16.6 Model-level details and constraints

#### User and OTP

```text
User
  id UUID PK
  phone_e164 unique, nullable until verified only if required
  full_name
  role enum(customer, admin, logistics, vendor)
  is_active
  created_at, updated_at

OtpChallenge
  id UUID PK
  phone_e164
  purpose enum(login, phone_change)
  code_hash
  expires_at
  attempt_count
  consumed_at nullable
  requested_ip_hash nullable
  created_at
```

Rules:

- Store phone numbers in E.164 form such as `+919876543210`.
- Hash OTP values; never store plaintext codes.
- Rate-limit requests by phone/IP/device and lock after a configured failed-attempt threshold.
- OTP verification is single-use, time-limited, and idempotent once a session is issued.

#### Order price snapshots

`ServicePrice` is mutable future configuration; an `AlterationItem` quote must remain an immutable snapshot after checkout.

```text
AlterationItem
  service_code_snapshot
  service_name_snapshot
  measurement_schema_version
  measurement_payload JSONB
  quoted_price_paise
  approved_price_paise nullable
  customer_instruction
```

Order totals must be calculated as:

```text
subtotal_paise = sum(final price of every alteration item × garment quantity)
total_paise = subtotal_paise + delivery_fee_paise - discount_paise
```

Never trust `subtotal_paise`, `total_paise`, or alteration price received from a client.

#### Order status transitions

Use an explicit transition map, tested as a matrix. Define allowed actors for every edge.

| From | To | Allowed actor |
|---|---|---|
| placed | pickup_assigned | admin |
| placed | cancelled | customer/admin |
| pickup_assigned | picked_up | assigned logistics/admin |
| pickup_assigned | pickup_failed | assigned logistics/admin |
| pickup_assigned | cancelled | admin |
| pickup_failed | pickup_assigned | admin |
| picked_up | at_vendor | assigned logistics/admin |
| at_vendor | alteration_complete | admin, later assigned vendor |
| at_vendor | customer_approval_needed | admin |
| at_vendor | rework_required | admin |
| customer_approval_needed | at_vendor | admin after approval |
| alteration_complete | ready_for_delivery | admin/assigned logistics |
| ready_for_delivery | out_for_delivery | assigned logistics/admin |
| out_for_delivery | delivered | assigned logistics/admin |
| delivered | rework_required | customer request + admin decision |

Do not expose a generic unrestricted `PATCH order.status` endpoint to customer or logistics clients.

#### Indexes and database constraints

Add database indexes deliberately:

```text
Order(customer_id, created_at DESC)
Order(logistics_partner_id, status, pickup_window)
Order(vendor_id, status)
Order(status, expected_delivery_date)
StatusEvent(order_id, created_at)
NotificationJob(state, created_at)
Payment(order_id, provider_payment_id unique)
Garment(qr_code unique)
```

Add `CheckConstraint`s for non-negative monetary values and valid quantity. Add uniqueness/idempotency constraints for webhooks and payment provider IDs.

### 16.7 API payloads and endpoint implementation order

#### Order quote request

```http
POST /api/v1/orders/quote
Authorization: Bearer <access-token>
```

```json
{
  "address_id": "uuid",
  "pickup_slot_id": "uuid",
  "garments": [
    {
      "garment_type": "trousers",
      "quantity": 1,
      "colour": "navy",
      "alterations": [
        {
          "service_code": "trousers.reduce_waist",
          "measurement": {
            "schema_version": 1,
            "measurement_mode": "alteration_delta",
            "unit": "in",
            "values": {"waist_reduce_by": 1}
          },
          "customer_instruction": "Keep the original waistband finish."
        }
      ]
    }
  ]
}
```

Quote response must return service validation results, line-item prices, fees, total, applicable terms, and a short-lived quote identifier. The server recomputes quote values when an order is created.

#### Create order request

```http
POST /api/v1/orders
Idempotency-Key: <client-generated UUID>
Authorization: Bearer <access-token>
```

The endpoint accepts an approved quote ID and same immutable request content. Persist the idempotency key per customer. A replay returns the original order rather than creating a duplicate.

#### Status action request

```http
POST /api/v1/logistics/orders/{order_id}/pickup-confirmation
Authorization: Bearer <access-token>
```

```json
{
  "garments": [
    {"garment_id": "uuid", "qr_code": "GRM-8F2K9Q", "condition_note": "No visible defects"}
  ],
  "proof_media_ids": ["uuid"],
  "note": "Collected from security desk"
}
```

The domain service must confirm the requester is the assigned logistics partner, all listed garments belong to the order, all expected garments are accounted for, and the transition is allowed.

#### API implementation sequence

1. Version API routes and introduce standardized error handler.
2. Implement account/OTP/session endpoints with fake provider in tests.
3. Implement catalogue, price, serviceability, pickup slots, and quote endpoint.
4. Implement idempotent customer order creation.
5. Implement media presign/finalize workflow.
6. Implement payment order/webhook.
7. Implement assignment and state-specific operations endpoints.
8. Implement notifications/outbox adapters and protected callback.
9. Publish OpenAPI schema and generate TypeScript client.

### 16.8 Payment implementation details

Use a `Payment` state machine separate from fulfillment status:

```text
created → pending → paid
                 ↘ failed
paid → refund_pending → refunded | refund_failed
```

Required mechanics:

- Backend creates Razorpay order with the server-calculated total and an internal order reference in notes.
- Client receives only Razorpay public checkout configuration/order ID.
- Treat only a signature-verified webhook as final payment authority.
- Store provider IDs, event IDs, amount, currency, state, and raw payload reference/hash.
- Deduplicate webhook events by provider event ID.
- Never mark an order `placed`/payable twice because a client retries or webhook is delivered twice.
- Implement payment/refund provider calls through `PaymentGateway` interface and `FakePaymentGateway` for tests.

### 16.9 Media implementation details

1. Client asks `POST /media/upload-url` with entity purpose, file name, MIME type, byte size, and checksum.
2. Backend authorizes entity ownership/access and returns a single-purpose presigned S3 PUT URL plus media ID.
3. Client uploads directly to S3.
4. Client calls `POST /media/{id}/complete`.
5. Backend verifies object metadata/head, persists final status, and links it to garment/order/proof.

Rules:

- Allowed formats: JPEG, PNG, HEIC only initially; configure max size/count.
- Generate server-owned object keys; never accept arbitrary S3 key/path from clients.
- Store checksum and uploader identity.
- Serve through short-lived signed GET URLs.
- Add malware scanning/event workflow only when launch risk/compliance requires it; do not claim it exists before then.

### 16.10 Frontend implementation details

#### Web technology

```text
Next.js App Router + TypeScript
React Hook Form + Zod for form state/validation
TanStack Query for API state/cache
Generated API client from OpenAPI
Tailwind or a documented component system
Playwright for browser E2E tests
```

#### Customer route map

```text
/                         landing/serviceability entry
/login                    phone OTP
/order/new                guarded multi-step order wizard
/order/new/address
/order/new/garments
/order/new/measurements
/order/new/review
/checkout/{orderId}
/orders
/orders/{orderNumber}
/measurements
/support
```

The order wizard must preserve draft state locally and server-side only after the customer chooses to save a draft. It must not create duplicate orders on browser refresh; use quote/order idempotency identifiers.

#### Admin route map

```text
/admin/orders
/admin/orders/{orderNumber}
/admin/exceptions
/admin/catalog/services
/admin/catalog/prices
/admin/vendors
/admin/logistics-partners
/admin/reports
```

#### Logistics route map (React Native)

```text
/(logistics)/today
/(logistics)/task/{orderId}
/(logistics)/scan
/(logistics)/proof
/(logistics)/failure
```

The client only renders permitted actions, but the backend remains the authority for all permissions and transitions.

### 16.11 CDK package implementation details

#### CDK file structure

```text
infra/cdk/
  bin/stitchcore.ts
  lib/config/environment.ts
  lib/stacks/foundation-stack.ts
  lib/stacks/data-stack.ts
  lib/stacks/compute-stack.ts
  lib/stacks/messaging-stack.ts
  lib/stacks/observability-stack.ts
  lib/constructs/database.ts
  lib/constructs/api-service.ts
  lib/constructs/notification-pipeline.ts
  test/*.test.ts
  cdk.json
  package.json
```

#### Environment configuration type

```ts
export type EnvironmentConfig = {
  name: "beta" | "production";
  account: string;
  region: "ap-south-1";
  domainName: string;
  apiDesiredCount: number;
  apiCpu: number;
  apiMemoryMiB: number;
  deletionProtection: boolean;
  backupRetentionDays: number;
  logRetentionDays: number;
};
```

Keep account IDs, domain values, and provider secrets out of source. Load non-secret deployment parameters through GitHub environment variables or CDK context files ignored by Git where necessary.

#### Required IAM permissions

ECS task role must be scoped to:

- Read only named Secrets Manager secrets.
- Read/write only the named media bucket/prefixes.
- Send only to notification queue.
- Write only its configured CloudWatch Logs group.

Notification Lambda role must be scoped to:

- Receive/delete from the named SQS queue.
- Read only its provider/API secrets.
- Invoke internal API through its intended network endpoint.
- Write to its log group.

Do not use administrator permissions for runtime ECS/Lambda roles.

### 16.12 GitHub Actions implementation details

#### Required workflows

```text
.github/workflows/ci.yml
.github/workflows/deploy-beta.yml
.github/workflows/deploy-production.yml
.github/workflows/nightly-security.yml
```

#### `ci.yml` jobs

```text
changed-files
backend-lint
backend-test
backend-migration-check
frontend-web-lint-test
frontend-mobile-lint-test
openapi-validate
docker-build
cdk-synth-beta
cdk-synth-production
security-secret-dependency-scan
```

Each job pins action versions, uses dependency cache keyed by lockfile, and uploads only non-sensitive test/coverage artifacts.

#### AWS authentication

Use GitHub Actions OIDC:

```text
GitHub environment (beta/production)
  → configured OIDC trust policy restricted to repository + branch/environment
  → IAM deployment role with CDK/ECR/ECS permissions appropriate to environment
```

No `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` secrets in GitHub Actions.

#### Deployment workflow pseudo-steps

```yaml
- checkout exact commit SHA
- setup Python and Node from locked versions
- install locked dependencies
- run tests/synth again
- configure AWS credentials through OIDC
- build and push ECR image with immutable SHA tag
- cdk deploy target environment
- run ECS migration task and wait for success
- force/update ECS deployment and wait for stable service
- run integration test suite against deployed API
- publish deployment summary
```

Production workflow additionally uses GitHub Environment `production` with required reviewers and accepts a release SHA/tag that already passed beta.

### 16.13 Integration test harness

Use a separate black-box test package under `tests/integration/`.

```text
tests/integration/
  pyproject.toml or package.json
  config.py
  clients/api_client.py
  clients/razorpay_fake.py
  clients/notification_recorder.py
  fixtures.py
  test_customer_order_journey.py
  test_fulfillment_journey.py
  test_authorization.py
  test_payment_webhook.py
  test_notification_retry.py
  test_media_upload.py
```

Required environment variables:

```dotenv
TEST_API_BASE_URL=https://api.beta.example.com
TEST_ADMIN_TOKEN=
TEST_CUSTOMER_PHONE=
TEST_LOGISTICS_PHONE=
TEST_VENDOR_PHONE=
TEST_RAZORPAY_WEBHOOK_SECRET=
```

Rules:

- Run destructive/seed/reset tests only against beta/local, never production.
- Use an API client with explicit timeouts, retry only idempotent read/poll operations, and clear assertion messages.
- Poll async notification state with bounded timeout rather than `sleep` alone.
- Store random run IDs in test-created customer/order labels to allow safe cleanup.
- Test SQS/Lambda adapters through provider mocks in CI and sandbox/test providers in beta.

### 16.14 Required verification commands by change type

| Change | Minimum verification |
|---|---|
| Django model/migration | `makemigrations --check`, migrate fresh DB, targeted tests, full backend test suite |
| State machine/permission | Unit transition matrix + API unauthorized/authorized tests |
| Payment/webhook | Signature/idempotency tests + fake-gateway integration test |
| SQS/Lambda | Unit adapter test + queue retry/DLQ integration test |
| Web UI | Type check, component tests, Playwright critical-flow test |
| Mobile UI | Type check, unit test, device/emulator smoke test where available |
| CDK | `cdk synth`, CDK assertions, `cdk diff` review |
| CI/CD | Workflow lint/dry run where available; beta deployment smoke test |

### 16.15 Work-item template

Every implementation task/PR should be written in this form:

```markdown
## Objective
One sentence describing the user/business outcome.

## Scope
- Included:
- Explicitly excluded:

## Files/modules expected to change
-

## API/data changes
- Request/response:
- Migration:
- Permission rule:

## Acceptance criteria
- [ ]

## Tests
- [ ] Unit
- [ ] API/integration
- [ ] Manual QA if applicable

## Rollout/rollback
- Feature flag/configuration:
- Migration compatibility:
```

### 16.16 First recommended implementation tickets

Execute in this exact order unless product owner changes priority:

1. **Developer environment:** Docker Compose, PostgreSQL, `.env.example`, Makefile, documented setup, CI Python test job.
2. **API foundation:** `/api/v1`, standardized errors, OpenAPI generation, API version tests.
3. **Authentication:** phone normalization, OTP challenge, fake OTP provider, access/refresh tokens, rate-limit tests.
4. **Catalogue and measurements:** service catalogue, service-specific JSON schema validation, price/serviceability endpoints, quote service.
5. **Idempotent order creation:** customer address authorization, quote snapshot, garment QR IDs, audit event, total calculation.
6. **Operational fulfillment:** admin assignment, role-scoped task list, pickup/vendor/delivery confirmation endpoints, proof metadata.
7. **Media:** S3 presign/finalize interfaces with fake/S3 adapters and media authorization tests.
8. **Payments:** Razorpay gateway interface, payment order creation, verified webhook, payment state machine.
9. **Notifications:** notification outbox, SQS publisher, Lambda adapter, mocks/retries/DLQ tests.
10. **Customer web:** order wizard end-to-end against beta API.
11. **CDK and beta:** deploy backend/data/messaging stack, run integration suite.
12. **Admin/logistics apps:** after core beta workflow is validated.

