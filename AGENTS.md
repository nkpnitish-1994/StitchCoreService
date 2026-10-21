# StitchCoreService — Product and Engineering Context

> `task.md` is the canonical implementation plan and execution checklist. Before implementing a feature, read the relevant sections of `task.md`; this file provides durable context and guardrails.

## Purpose

StitchCore is a convenience platform for clothing alterations. Customers submit clothes that do not fit well, describe the alteration and measurements, arrange collection, and receive the altered garments back. The service manages pickup, delivery to an alteration vendor, return pickup, and final delivery.

The initial product is deliberately operations-led: many decisions are made manually by the admin and logistics partner rather than by automated routing, vendor allocation, or quality systems.

## Launch model

- Start in one tightly bounded city locality/service area to make bulk logistics economical.
- Use one trusted vendor initially, expanding only after quality and turnaround are proven.
- Use one or two logistics partners.
- Batch pickup orders in the evening (for example, 5 PM), hand the batch to the vendor, collect completed garments the next day, then deliver them in bulk.
- Prioritize standard, clearly priced work: trouser hemming/waist, shirt sleeve/side fitting, kurta adjustments, dress hemming.
- Do not initially accept complex redesigns, expensive weddingwear, leather, or other high-risk garments.

## Product roles

### Customer

- Sign in by phone/OTP (development challenge/verification exists; production provider remains pending). Restricted beta uses explicitly provisioned test accounts.
- Save pickup/delivery addresses.
- Create an order with one or more garments.
- Choose an alteration service, give exact instructions/measurements, add notes and photos, and select a pickup slot.
- Track order status and receive notifications.
- Eventually pay online through Razorpay and request a rework where permitted.

### Admin

- View all orders and their complete status history.
- Assign a logistics partner and vendor manually.
- Handle price exceptions, cancellations, rework, and customer support.
- Use Django Admin in the first release; a custom operations dashboard can follow.

### Logistics partner

- View only orders assigned to them.
- Perform pickup and delivery tasks.
- Confirm garment count, scan/record garment QR identity, add proof photo/URL and notes.
- Manually progress status for the orders they handle.
- Receive a WhatsApp route/task summary; routes remain manually created.

### Alteration vendor

- Is coordinated manually by admin/logistics at MVP stage.
- Does not need an app or portal at launch.
- May receive a WhatsApp message or a simple job list later; automatic job-sheet generation is not required now.

## Customer order experience

The customer experience should feel premium and finish an order in roughly three minutes:

1. Phone sign-in.
2. Add/select pickup address.
3. Add one or more garments.
4. Choose a structured alteration (for example, `reduce_waist` or `shorten_length`).
5. Add measurement data, reference photos, or choose a measurement-at-pickup option.
6. See clear prices and expected return date.
7. Confirm pickup window and pay when Razorpay is integrated.
8. Track progress in the app/site.

Ask for only the measurements that are needed. Customers should be able to express a standard request such as “reduce waist by 1 inch” rather than complete a lengthy full-body measurement form.

## Manual operations flow

1. Customer creates an order.
2. Admin manually assigns a logistics partner (and normally a vendor).
3. Logistics partner performs a pickup route and marks each order `picked_up` after verifying garments/proof.
4. Logistics partner or admin marks the order `at_vendor` after physical handover.
5. Admin or logistics partner manually marks vendor completion and delivery readiness.
6. Logistics partner collects completed garments and marks them `out_for_delivery`.
7. Logistics partner marks the order `delivered`, ideally with delivery proof.

No automatic routing, automatic vendor assignment, automatic quality inspection, automatic vendor job-sheet generation, or scheduled route dispatch is in scope for the MVP. Quality checks are manual and should be captured with status notes/proof where useful.

## Order lifecycle

Main flow:

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

Exception states:

```text
pickup_failed
customer_approval_needed
rework_required
cancelled
```

State changes must be validated, recorded immutably in `StatusEvent`, attributed to the acting user, and include an optional note and proof URL. A logistics partner may update only orders assigned to them.

## Garment custody and quality

- Every garment gets a unique QR-friendly identifier such as `GRM-8F2K9Q`.
- Every customer order gets a customer-facing identifier such as `ORD-20261020-00124`.
- Capture pickup condition/photos and delivery proof where appropriate.
- Preserve an audit trail of custody/status to prevent garment mix-ups and resolve disputes.
- Plan for a transparent rework policy, such as one free correction within a defined time window, but keep the policy configurable/manual initially.

## Confirmed architecture

```text
Customer iOS/Android app + customer website
                 │
                 ▼
Django REST API on AWS ECS Fargate (Sydney, ap-southeast-2)
                 │
     ┌───────────┼────────────┐
     ▼           ▼            ▼
RDS PostgreSQL  S3          SQS notification queue
                              │
                              ▼
                      AWS Lambda notification sender
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
       WhatsApp Business      FCM          SMS fallback
```

### Explicit non-decision: Redis/Celery

Do **not** introduce Redis or Celery for this MVP. There are no required recurring operational jobs. Notifications are the only background work, so use SQS plus an SQS-triggered Lambda instead of a permanently running worker.

### AWS deployment components

- **ECS Fargate:** one Django API task initially; begin around 0.5 vCPU / 1 GB RAM.
- **RDS PostgreSQL:** production database and sole system of record.
- **S3:** private storage for garment/pickup/delivery images; use signed access, not public object URLs.
- **SQS:** durable notification message queue.
- **Lambda:** consumes SQS and sends notifications; SQS retries failures and can use a dead-letter queue.
- **CloudWatch:** logs, alarms, and error monitoring.
- **Secrets Manager / Parameter Store:** production secrets; never commit credentials.
- **Avoid a NAT Gateway in the earliest MVP unless truly needed:** it can become a disproportionate cost.

### Notifications

- **Push:** Firebase Cloud Messaging for Android, iOS (via APNs), and web.
- **WhatsApp:** WhatsApp Business Platform through Meta directly or a chosen BSP (for example, Interakt/Gupshup/Twilio); use approved templates where required.
- **SMS:** OTP and urgent fallback only; do not use it for every status update.
- **Email:** optional for receipts and non-urgent records.

Notification delivery follows this pattern:

```text
Manual status change
  → Django transaction saves order + StatusEvent + NotificationJob in PostgreSQL
  → on successful commit, publish a minimal delivery payload to SQS
  → Lambda calls WhatsApp/FCM/SMS provider
  → Lambda calls the protected Django internal callback to record sent/failed state
```

Do not put sensitive full addresses into plain WhatsApp messages. Logistics partners should open an authenticated task view or short-lived secure link.

## Backend implementation status

The repository already contains a Django REST foundation:

- Custom `User` model with `customer`, `logistics`, `admin`, and `vendor` roles.
- `Address`, `Vendor`, `Order`, `Garment`, `AlterationItem`, `StatusEvent`, `NotificationJob`, and `DeviceToken` models.
- Customer address/order APIs.
- Role-scoped order listing/detail access.
- Manual status update API with transition validation.
- Admin vendor/logistics assignment API.
- Django Admin setup for initial operational use.
- SQS publisher and an SQS Lambda notification-adapter skeleton.
- Dockerfile suited to a Django container on ECS Fargate.
- Initial workflow test.
- Basic catalogue/quotes, server-priced idempotent order creation, development OTP/JWT and restricted beta sign-in.
- API-connected customer web ordering/history/timeline and an operations queue with audited assignment/status controls.
- Expo screen scaffolds, CDK infrastructure and deployment preparation; deployed status is tracked in `task.md`.

The provider adapters are intentionally not live yet. They need selected provider accounts/credentials for WhatsApp, FCM, Razorpay, S3, SQS, Lambda, and RDS before production integration.

## Data model

```text
User
  ├── Address
  ├── Order (customer)
  └── Order (assigned logistics partner)

Order
  ├── Garment
  │     └── AlterationItem
  ├── StatusEvent
  ├── NotificationJob
  ├── Address
  └── Vendor
```

All prices are stored in paise, not floating-point rupees. Measurement data is structured JSON per alteration item so the UI can evolve without constantly changing database columns.

## API direction

Current route families:

```text
/api/v1/addresses/
/api/v1/orders/
/api/v1/orders/{id}/status/
/api/v1/orders/{id}/assign/
/api/v1/device-tokens/
/api/v1/internal/notifications/{job_id}/delivery/
```

The internal notification callback is not a public client API. Protect it with an internal secret (and, in production, network restrictions/IAM where appropriate).

## Client applications to build next

1. Customer mobile apps: one cross-platform React Native/Expo app for iOS and Android.
2. Customer website: Next.js responsive ordering and tracking site.
3. Admin operations interface: begin with Django Admin; create a polished Next.js dashboard after workflows stabilize.
4. Logistics mode: a role-based section in the same mobile app with today’s tasks, order details, status action buttons, map/call actions, garment scan, and proof capture.

Prefer one shared API contract and design system. Do not create three separate backends or duplicate business logic in clients.

## Security and reliability requirements

- Use a secure phone OTP flow before production launch.
- Enforce server-side role and object permissions; never rely solely on hidden UI controls.
- Keep customer phone/address data visible only to relevant staff and assigned logistics partners.
- Use signed upload/download URLs for garment photos in S3.
- Validate all order status transitions on the server.
- Save orders before publishing notification work; SQS/Lambda failure must not lose order data.
- Never commit secrets, API keys, AWS credentials, or provider tokens.
- Use PostgreSQL/RDS in production; SQLite is local development only.

## Engineering conventions

- Python + Django + Django REST Framework for the backend.
- PostgreSQL is the permanent source of truth.
- Use Django service functions for workflow/state transitions; do not put complex workflow logic in views or clients.
- Keep API responses and error messages explicit and predictable for mobile/web clients.
- Add tests for each new state transition, permission rule, and external-integration failure case.
- Preserve existing user changes; this repository began as an empty workspace and now contains the backend MVP.

## Out of scope for the first MVP

- Automated route optimization.
- Live driver GPS tracking.
- Automated vendor allocation.
- Automated quality checks.
- Vendor app/portal.
- AI measurement extraction.
- Complex dynamic pricing.
- Multi-city/multi-vendor operational automation.
