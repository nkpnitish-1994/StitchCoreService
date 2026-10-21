# Beta deployment

## Current state

Deployment has **not** succeeded. The authenticated CloudShell AWS role is denied
CloudFormation access in Mumbai by organization service control policy
`p-b185vfbk`. The organization administrator must allow the application services
and CDK bootstrap/deployment roles in `ap-south-1`, or supply an account where
Mumbai is allowed. The owner subsequently authorized Sydney (`ap-southeast-2`); the deployment now
targets Sydney.

The website is an early scaffold: login requires an OTP provider, the order page
currently requests a quote, and customer tracking/checkout still need implementation.
Deploying the containers does not make the complete customer journey launch-ready.
Payments, private media uploads, and real WhatsApp/FCM delivery remain unfinished.

## Deployment layout

CloudFront supplies the default HTTPS hostname. It forwards dynamic requests
without caching to an ALB protected by a generated origin header. The ALB routes
`/api/*`, `/admin/*`, `/static/*`, and `/health/` to Django and other paths to Next.js.
The web client uses the same-origin `/api/v1` API, avoiding CORS configuration.

One Fargate task contains web and API containers, initially totaling 0.5 vCPU / 1 GB.
Public-subnet tasks have outbound internet access and accept inbound traffic only
from the load balancer. RDS PostgreSQL is private and encrypted. No NAT gateway is
created. Application, database, internal-callback, and origin secrets are separate
Secrets Manager secrets. Images are immutable CDK Docker assets in bootstrap ECR.

S3 remains private. SQS and its DLQ are provisioned, but the notification Lambda has
no event source until real providers are configured and their retry behavior is
tested. The skeleton raises instead of falsely recording successful delivery.
Phone OTP requests return 503 when a production provider is unavailable.

## Prerequisites

- AWS access to the approved account in `ap-southeast-2`, including CDK bootstrap,
  CloudFormation, ECS, ECR, EC2, ELB, CloudFront, RDS, S3, SQS, Lambda, IAM,
  Secrets Manager, and CloudWatch.
- Python 3.12+, Node 22+, Docker with internet access, AWS CLI v2.
- A selected OTP provider and credentials, or an explicitly approved restricted
  beta authentication design before opening customer access.
- A reviewed CDK diff and cost/resource configuration.

## Prepare and verify

From the repository root:

```bash
python -m pip install -r requirements-prod.txt
python manage.py test
python manage.py makemigrations --check --dry-run
cd frontend/web
npm ci
npm run typecheck
npm run build
cd ../../infra/cdk
npm ci
npm run build
npm test
npx cdk synth -c env=beta
npx cdk synth -c env=production
npx cdk diff -c env=beta
```

Use `--output /tmp/stitchcore-cdk-beta` on CloudShell if home storage is limited.
Docker images and Node dependencies should be built outside the small home volume
when necessary. npm's `package-lock.json` is the lockfile used by images and CI.

## First deployment

After the organization policy is resolved, bootstrap the approved account and
region once using the account's configured deployment role:

```bash
cd infra/cdk
npx cdk bootstrap
cd ../..
python scripts/deploy_beta.py --initialize
```

Configure AWS_DEFAULT_REGION=ap-southeast-2 and AWS_REGION=ap-southeast-2 for bootstrap.
The stack itself always targets Sydney. The script fails on missing bootstrap
before creating application resources.

The script builds/publishes the web and API image assets, creates the beta stack
with zero service tasks, runs an isolated Fargate migration task, and checks its
exit code. PostgreSQL advisory locking serializes concurrent migrations. Only
after success does the script start the service, wait for stability, and verify
the homepage, database health, and catalogue over the emitted HTTPS hostname.

It does not seed customer/admin accounts, create default passwords, integrate
payment, or send notifications. Obtain admin access through an authorized one-off
ECS management task; do not publish staff credentials or tokens in logs.

For subsequent backwards-compatible releases:

```bash
python scripts/deploy_beta.py
```

Never use `--initialize` on an existing running environment: it scales the service
to zero for first-time setup. Initial failures after infrastructure creation should
be diagnosed through CloudFormation events and the migration CloudWatch log group;
do not delete RDS to retry.

## Rollback and verification limits

ECS deployment circuit breakers roll back unhealthy service revisions. Re-deploy
the prior reviewed Git revision to roll back application code; migrations must
remain backwards compatible and use forward fixes. Database snapshots and media
are retained on stack deletion. Never automatically delete beta/production data.

Live CDK diff, resource deployment, database connectivity, and external HTTPS smoke
checks remain unverified until AWS permits deployment. Local builds and template
assertions do not establish that the website is live. Production deployment remains
subject to its separate beta-validation and approval gate.
