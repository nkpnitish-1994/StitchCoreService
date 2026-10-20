"""SQS-triggered Lambda for notification delivery.

Provider calls are intentionally isolated here. Configure WhatsApp/FCM credentials
as Lambda environment variables or, preferably, fetch them from Secrets Manager.
"""
import json
import logging
import os
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)
API_BASE_URL = os.environ["INTERNAL_API_BASE_URL"].rstrip("/")
INTERNAL_SECRET = os.environ["INTERNAL_NOTIFICATION_SECRET"]


def handler(event, context):
    for record in event["Records"]:
        job = json.loads(record["body"])
        job_id = job["notification_job_id"]
        try:
            # Replace this adapter with the chosen WhatsApp BSP / FCM integration.
            provider_id = deliver(job)
            report(job_id, "sent", provider_message_id=provider_id)
        except Exception:
            logger.exception("Unable to deliver notification %s", job_id)
            # Raising causes SQS to retry and eventually send this record to its DLQ.
            raise


def deliver(job):
    """Provider adapter boundary. Implement after choosing Meta/BSP and FCM credentials."""
    logger.info("Delivering %s notification %s", job["channel"], job["notification_job_id"])
    return f"pending-provider-{job['notification_job_id']}"


def report(job_id, state, **data):
    body = json.dumps({"state": state, **data}).encode()
    request = urllib.request.Request(
        f"{API_BASE_URL}/api/internal/notifications/{job_id}/delivery/",
        data=body,
        headers={"Content-Type": "application/json", "X-Internal-Secret": INTERNAL_SECRET},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        if response.status >= 300:
            raise RuntimeError(f"Notification callback failed with {response.status}")
