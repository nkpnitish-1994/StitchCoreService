import uuid
from datetime import timedelta
from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        LOGISTICS = "logistics", "Logistics partner"
        ADMIN = "admin", "Admin"
        VENDOR = "vendor", "Vendor"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=20, blank=True)

    @property
    def is_ops_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN


class OtpChallenge(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.LOGIN)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, phone, code):
        return cls.objects.create(phone=phone, code_hash=make_password(code), expires_at=timezone.now() + timedelta(minutes=10))

    def consume(self, code):
        if self.consumed_at or timezone.now() > self.expires_at or self.attempts >= 5:
            return False
        self.attempts += 1
        if not check_password(code, self.code_hash):
            self.save(update_fields=["attempts"])
            return False
        self.consumed_at = timezone.now()
        self.save(update_fields=["attempts", "consumed_at"])
        return True


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, default="Home")
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=20)
    landmark = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    def __str__(self):
        return f"{self.label}: {self.line1}"


class Vendor(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Service(models.Model):
    GARMENT_TYPES = (("trousers", "Trousers"), ("shirt", "Shirt"), ("kurta", "Kurta"), ("dress", "Dress"), ("other", "Other"))
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=120)
    garment_type = models.CharField(max_length=20, choices=GARMENT_TYPES)
    base_price_paise = models.PositiveIntegerField()
    measurement_schema = models.JSONField(default=dict)
    active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["garment_type", "active"])]


class PickupSlot(models.Model):
    label = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=20)
    active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["starts_at", "active"])]


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        PICKUP_ASSIGNED = "pickup_assigned", "Pickup assigned"
        PICKED_UP = "picked_up", "Picked up"
        AT_VENDOR = "at_vendor", "At vendor"
        ALTERATION_COMPLETE = "alteration_complete", "Alteration complete"
        READY_FOR_DELIVERY = "ready_for_delivery", "Ready for delivery"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        PICKUP_FAILED = "pickup_failed", "Pickup failed"
        CUSTOMER_APPROVAL_NEEDED = "customer_approval_needed", "Customer approval needed"
        REWORK_REQUIRED = "rework_required", "Rework required"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=32, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="orders")
    logistics_partner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_orders")
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PLACED)
    pickup_window = models.CharField(max_length=100)
    pickup_slot = models.ForeignKey(PickupSlot, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    expected_delivery_date = models.DateField(null=True, blank=True)
    subtotal_paise = models.PositiveIntegerField(default=0)
    delivery_fee_paise = models.PositiveIntegerField(default=0)
    discount_paise = models.PositiveIntegerField(default=0)
    idempotency_key = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_paise(self):
        return self.subtotal_paise + self.delivery_fee_paise - self.discount_paise

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["logistics_partner", "status"]),
            models.Index(fields=["vendor", "status"]),
            models.Index(fields=["status", "expected_delivery_date"]),
        ]
        constraints = [models.UniqueConstraint(fields=["customer", "idempotency_key"], name="unique_customer_idempotency_key")]

    def __str__(self):
        return self.order_number


class Garment(models.Model):
    class Type(models.TextChoices):
        TROUSERS = "trousers", "Trousers"
        SHIRT = "shirt", "Shirt"
        KURTA = "kurta", "Kurta"
        DRESS = "dress", "Dress"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="garments")
    garment_type = models.CharField(max_length=20, choices=Type.choices)
    colour = models.CharField(max_length=60, blank=True)
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    qr_code = models.CharField(max_length=40, unique=True, editable=False)
    pickup_photo_url = models.URLField(blank=True)
    condition_notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.qr_code:
            self.qr_code = f"GRM-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class AlterationItem(models.Model):
    garment = models.ForeignKey(Garment, on_delete=models.CASCADE, related_name="alterations")
    service_code = models.CharField(max_length=80)
    service_name_snapshot = models.CharField(max_length=120, blank=True)
    measurement_schema_version = models.PositiveSmallIntegerField(default=1)
    measurement_data = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    quoted_price_paise = models.PositiveIntegerField(default=0)
    approved_price_paise = models.PositiveIntegerField(null=True, blank=True)


class StatusEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_events")
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32, choices=Order.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    note = models.TextField(blank=True)
    proof_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationJob(models.Model):
    class Channel(models.TextChoices):
        PUSH = "push", "Push"
        WHATSAPP = "whatsapp", "WhatsApp"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="notification_jobs")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    template_code = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    provider_message_id = models.CharField(max_length=255, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class DeviceToken(models.Model):
    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"
        WEB = "web", "Web"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    platform = models.CharField(max_length=10, choices=Platform.choices)
    token = models.CharField(max_length=512, unique=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)


class MediaAsset(models.Model):
    class Purpose(models.TextChoices):
        GARMENT = "garment", "Garment"
        PICKUP_PROOF = "pickup_proof", "Pickup proof"
        DELIVERY_PROOF = "delivery_proof", "Delivery proof"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    s3_key = models.CharField(max_length=512, unique=True)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    checksum = models.CharField(max_length=128, blank=True)
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Payment(models.Model):
    class State(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUND_PENDING = "refund_pending", "Refund pending"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    provider_order_id = models.CharField(max_length=128, unique=True)
    provider_payment_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    state = models.CharField(max_length=20, choices=State.choices, default=State.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
