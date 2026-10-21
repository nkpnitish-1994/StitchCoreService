import secrets
from datetime import timedelta
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Address, DeviceToken, NotificationJob, OtpChallenge, Order, Service
from .permissions import CanAccessOrder, IsOpsAdmin
from .serializers import AddressSerializer, AssignmentSerializer, CreateOrderSerializer, DeviceTokenSerializer, NotificationDeliverySerializer, OrderSerializer, OtpRequestSerializer, OtpVerifySerializer, QuoteSerializer, ServiceSerializer, StatusChangeSerializer
from .services import update_order_status


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = (IsAuthenticated,)
    queryset = Address.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = (IsAuthenticated, CanAccessOrder)
    filterset_fields = ("status",)
    queryset = Order.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        user = self.request.user
        queryset = Order.objects.select_related("customer", "address", "logistics_partner", "vendor").prefetch_related("garments__alterations", "status_events__changed_by")
        if user.is_ops_admin:
            return queryset
        return queryset.filter(Q(customer=user) | Q(logistics_partner=user))

    def get_serializer_class(self):
        return CreateOrderSerializer if self.action == "create" else OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def status(self, request, pk=None):
        order = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not (request.user.is_ops_admin or request.user.role == "logistics"):
            return Response({"detail": "Only operations staff can update an order."}, status=status.HTTP_403_FORBIDDEN)
        try:
            update_order_status(order=order, actor=request.user, to_status=serializer.validated_data["status"], note=serializer.validated_data.get("note", ""), proof_url=serializer.validated_data.get("proof_url", ""))
        except (ValueError, PermissionError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=["post"], permission_classes=[IsOpsAdmin])
    def assign(self, request, pk=None):
        order = self.get_object()
        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = {}
        if "logistics_partner_id" in serializer.validated_data:
            values["logistics_partner"] = serializer.validated_data["logistics_partner_id"]
        if "vendor_id" in serializer.validated_data:
            values["vendor"] = serializer.validated_data["vendor_id"]
        for field, value in values.items():
            setattr(order, field, value)
        if values:
            order.save(update_fields=[*values.keys(), "updated_at"])
        return Response(OrderSerializer(order).data)


class DeviceTokenViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = DeviceTokenSerializer

    def create(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        DeviceToken.objects.update_or_create(token=serializer.validated_data["token"], defaults={"user": request.user, "platform": serializer.validated_data["platform"], "active": True})
        return Response(status=status.HTTP_204_NO_CONTENT)


class InternalNotificationDeliveryViewSet(viewsets.ViewSet):
    """Callback used only by the SQS-triggered Lambda after a provider attempt."""
    authentication_classes = ()
    permission_classes = ()
    serializer_class = NotificationDeliverySerializer

    def create(self, request, job_id=None):
        if not settings.INTERNAL_NOTIFICATION_SECRET or request.headers.get("X-Internal-Secret") != settings.INTERNAL_NOTIFICATION_SECRET:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        job = NotificationJob.objects.get(pk=job_id)
        serializer = NotificationDeliverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = serializer.validated_data["state"]
        job.state = state
        job.provider_message_id = serializer.validated_data.get("provider_message_id", "")
        job.failure_reason = serializer.validated_data.get("failure_reason", "")
        job.save(update_fields=["state", "provider_message_id", "failure_reason"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=OtpRequestSerializer, responses={202: OpenApiTypes.OBJECT})
class OtpRequestView(APIView):
    permission_classes = ()
    authentication_classes = ()

    def post(self, request):
        serializer = OtpRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        recent = OtpChallenge.objects.filter(phone=phone, created_at__gte=timezone.now() - timedelta(minutes=1)).count()
        if recent >= 3:
            return Response({"code": "otp_rate_limited", "message": "Try again in a minute.", "fields": {}}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        code = f"{secrets.randbelow(1_000_000):06d}"
        OtpChallenge.issue(phone, code)
        if settings.DEBUG and settings.OTP_PROVIDER == "console":
            # Deliberately never return this in API responses; local development can inspect server logs.
            print(f"StitchCore development OTP for {phone}: {code}")
        return Response({"message": "OTP sent", "expires_in_seconds": 600}, status=status.HTTP_202_ACCEPTED)


@extend_schema(request=OtpVerifySerializer, responses={200: OpenApiTypes.OBJECT})
class OtpVerifyView(APIView):
    permission_classes = ()
    authentication_classes = ()

    def post(self, request):
        serializer = OtpVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        challenge = OtpChallenge.objects.filter(phone=phone, consumed_at__isnull=True).order_by("-created_at").first()
        if not challenge or not challenge.consume(serializer.validated_data["code"]):
            return Response({"code": "invalid_otp", "message": "The OTP is invalid or expired.", "fields": {"code": ["Invalid or expired OTP"]}}, status=status.HTTP_400_BAD_REQUEST)
        user, _ = __import__("operations.models", fromlist=["User"]).User.objects.get_or_create(username=phone, defaults={"phone": phone, "role": "customer", "first_name": serializer.validated_data.get("full_name", "")})
        if not user.is_active:
            return Response({"code": "account_inactive", "message": "This account is inactive.", "fields": {}}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": {"id": user.id, "phone": user.phone, "role": user.role, "name": user.get_full_name()}})


@extend_schema(responses=ServiceSerializer(many=True))
class ServiceListView(APIView):
    permission_classes = ()
    authentication_classes = ()

    def get(self, request):
        return Response(ServiceSerializer(Service.objects.filter(active=True).order_by("garment_type", "name"), many=True).data)


@extend_schema(request=QuoteSerializer, responses={200: OpenApiTypes.OBJECT})
class QuoteView(APIView):
    def post(self, request):
        serializer = QuoteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        lines, total = [], 0
        for garment in serializer.validated_data["garments"]:
            quantity = max(1, int(garment.get("quantity", 1)))
            for alteration in garment["alterations"]:
                try:
                    service = Service.objects.get(code=alteration["service_code"], active=True, garment_type=garment["garment_type"])
                except Service.DoesNotExist:
                    return Response({"code": "unsupported_service", "message": f"Unsupported service {alteration['service_code']}.", "fields": {}}, status=status.HTTP_400_BAD_REQUEST)
                price = service.base_price_paise * quantity
                lines.append({"service_code": service.code, "service_name": service.name, "quantity": quantity, "price_paise": price})
                total += price
        return Response({"line_items": lines, "subtotal_paise": total, "delivery_fee_paise": 0, "discount_paise": 0, "total_paise": total, "currency": "INR"})
