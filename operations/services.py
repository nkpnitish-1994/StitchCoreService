import json
import logging
import boto3
from django.conf import settings
from django.db import transaction
from .models import NotificationJob, Order, StatusEvent

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {
    Order.Status.PLACED: {Order.Status.PICKUP_ASSIGNED, Order.Status.CANCELLED},
    Order.Status.PICKUP_ASSIGNED: {Order.Status.PICKED_UP, Order.Status.PICKUP_FAILED, Order.Status.CANCELLED},
    Order.Status.PICKUP_FAILED: {Order.Status.PICKUP_ASSIGNED, Order.Status.CANCELLED},
    Order.Status.PICKED_UP: {Order.Status.AT_VENDOR},
    Order.Status.AT_VENDOR: {Order.Status.ALTERATION_COMPLETE, Order.Status.CUSTOMER_APPROVAL_NEEDED, Order.Status.REWORK_REQUIRED},
    Order.Status.CUSTOMER_APPROVAL_NEEDED: {Order.Status.AT_VENDOR, Order.Status.CANCELLED},
    Order.Status.REWORK_REQUIRED: {Order.Status.AT_VENDOR, Order.Status.ALTERATION_COMPLETE},
    Order.Status.ALTERATION_COMPLETE: {Order.Status.READY_FOR_DELIVERY},
    Order.Status.READY_FOR_DELIVERY: {Order.Status.OUT_FOR_DELIVERY},
    Order.Status.OUT_FOR_DELIVERY: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: {Order.Status.REWORK_REQUIRED},
    Order.Status.CANCELLED: set(),
}


def update_order_status(*, order, actor, to_status, note="", proof_url=""):
    if to_status not in VALID_TRANSITIONS[order.status]:
        raise ValueError(f"Cannot change {order.status} to {to_status}.")
    if actor.role == "logistics" and order.logistics_partner_id != actor.id:
        raise PermissionError("You can only update orders assigned to you.")
    old_status = order.status
    with transaction.atomic():
        order.status = to_status
        order.save(update_fields=["status", "updated_at"])
        StatusEvent.objects.create(order=order, from_status=old_status, to_status=to_status, changed_by=actor, note=note, proof_url=proof_url)
        for channel in (NotificationJob.Channel.PUSH, NotificationJob.Channel.WHATSAPP):
            job = NotificationJob.objects.create(
                order=order, recipient=order.customer, channel=channel,
                template_code=f"order_{to_status}",
                payload={"order_number": order.order_number, "status": to_status},
            )
            transaction.on_commit(lambda job_id=str(job.id): enqueue_notification(job_id))
    return order


def enqueue_notification(job_id):
    if not settings.NOTIFICATION_QUEUE_URL:
        logger.info("Notification %s created; no SQS queue is configured.", job_id)
        return
    job = NotificationJob.objects.select_related("recipient").get(pk=job_id)
    boto3.client("sqs", region_name=settings.AWS_REGION).send_message(
        QueueUrl=settings.NOTIFICATION_QUEUE_URL,
        MessageBody=json.dumps({
            "notification_job_id": job_id,
            "channel": job.channel,
            "recipient_phone": job.recipient.phone,
            "payload": job.payload,
        }),
    )
