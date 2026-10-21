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
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if not actor.is_ops_admin:
            if actor.role != "logistics" or locked.logistics_partner_id != actor.id:
                raise PermissionError("You can only update orders assigned to you.")
            logistics_edges = {
                ("pickup_assigned", "picked_up"), ("pickup_assigned", "pickup_failed"),
                ("picked_up", "at_vendor"), ("alteration_complete", "ready_for_delivery"),
                ("ready_for_delivery", "out_for_delivery"), ("out_for_delivery", "delivered"),
            }
            if (locked.status, to_status) not in logistics_edges:
                raise PermissionError("This action requires an administrator.")
        if to_status not in VALID_TRANSITIONS[locked.status]:
            raise ValueError(f"Cannot change {locked.status} to {to_status}.")
        old_status = locked.status
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
    try:
        boto3.client("sqs", region_name=settings.AWS_REGION).send_message(
            QueueUrl=settings.NOTIFICATION_QUEUE_URL,
            MessageBody=json.dumps({
                "notification_job_id": job_id,
                "channel": job.channel,
                "recipient_phone": job.recipient.phone,
                "payload": job.payload,
            }),
        )
    except Exception:
        # PostgreSQL retains the pending job; queue failure must not fail a saved action.
        logger.exception("Notification queue publish failed for job %s", job_id)


def assign_order(*, order, actor, logistics_partner=None, vendor=None):
    if not actor.is_ops_admin:
        raise PermissionError("Only administrators can assign orders.")
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status in {"delivered", "cancelled"}:
            raise ValueError("Completed orders cannot be reassigned.")
        if logistics_partner is not None:
            if logistics_partner.role != "logistics" or not logistics_partner.is_active:
                raise ValueError("Choose an active logistics partner.")
            locked.logistics_partner = logistics_partner
        if vendor is not None:
            if not vendor.active:
                raise ValueError("Choose an active vendor.")
            locked.vendor = vendor
        locked.save(update_fields=["logistics_partner", "vendor", "updated_at"])
        StatusEvent.objects.create(order=locked, from_status=locked.status, to_status=locked.status,
                                   changed_by=actor, note=f"Assignment: logistics={locked.logistics_partner_id}; vendor={locked.vendor_id}")
        if locked.status in {"placed", "pickup_failed"} and locked.logistics_partner_id:
            update_order_status(order=locked, actor=actor, to_status="pickup_assigned", note="Pickup assigned by operations")
    order.refresh_from_db()
    return order


def price_garments(garments):
    """Resolve active catalogue prices. Client-supplied prices are never authoritative."""
    from copy import deepcopy
    from rest_framework.exceptions import ValidationError
    from .models import Service
    result = deepcopy(garments)
    for garment in result:
        for item in garment["alterations"]:
            try:
                service = Service.objects.get(code=item["service_code"], garment_type=garment["garment_type"], active=True)
            except Service.DoesNotExist as exc:
                raise ValidationError({"garments": ["Choose an active alteration supported for this garment."]}) from exc
            item["quoted_price_paise"] = service.base_price_paise
            item["service_name_snapshot"] = service.name
    return result


def order_content(address, pickup_window, garments, expected_delivery_date=None):
    """Canonical customer content for safe idempotency replay comparisons."""
    import json
    normalized = []
    for garment in garments:
        items = sorted(json.dumps({
            "code": item["service_code"], "measurement": item.get("measurement_data", {}),
            "notes": item.get("notes", ""),
        }, sort_keys=True) for item in garment["alterations"])
        normalized.append(json.dumps({
            "type": garment["garment_type"], "colour": garment.get("colour", ""),
            "quantity": garment.get("quantity", 1), "items": items,
        }, sort_keys=True))
    return str(address.pk), pickup_window, str(expected_delivery_date or ""), sorted(normalized)


def create_customer_order(*, customer, address, pickup_window, garments, expected_delivery_date=None, idempotency_key=None):
    from rest_framework.exceptions import PermissionDenied, ValidationError
    from .models import AlterationItem, Garment, User
    if customer.role != User.Role.CUSTOMER:
        raise PermissionDenied("Only customers can create pickup requests.")
    if address.user_id != customer.id:
        raise PermissionDenied("Choose one of your saved addresses.")
    with transaction.atomic():
        # Serialize writes for this customer, including first use of an idempotency key.
        User.objects.select_for_update().get(pk=customer.pk)
        if idempotency_key:
            previous = Order.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
            if previous:
                saved_garments = [{
                    "garment_type": g.garment_type, "colour": g.colour, "quantity": g.quantity,
                    "alterations": list(g.alterations.values("service_code", "measurement_data", "notes")),
                } for g in previous.garments.prefetch_related("alterations")]
                if order_content(address, pickup_window, garments, expected_delivery_date) != order_content(
                    previous.address, previous.pickup_window, saved_garments, previous.expected_delivery_date
                ):
                    raise ValidationError({"idempotency_key": ["This key was used for different order details."]})
                previous._replayed = True
                return previous
        garments = price_garments(garments)
        subtotal = sum(item["quoted_price_paise"] * g.get("quantity", 1) for g in garments for item in g["alterations"])
        order = Order.objects.create(
            customer=customer, address=address, pickup_window=pickup_window,
            expected_delivery_date=expected_delivery_date, subtotal_paise=subtotal, idempotency_key=idempotency_key,
        )
        for garment_data in garments:
            alterations = garment_data.pop("alterations")
            garment = Garment.objects.create(order=order, **garment_data)
            for item in alterations:
                AlterationItem.objects.create(garment=garment, **item)
        StatusEvent.objects.create(order=order, from_status="", to_status=Order.Status.PLACED,
                                   changed_by=customer, note="Order placed")
        return order
