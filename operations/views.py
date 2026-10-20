from django.conf import settings
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Address, DeviceToken, NotificationJob, Order
from .permissions import CanAccessOrder, IsOpsAdmin
from .serializers import AddressSerializer, AssignmentSerializer, CreateOrderSerializer, DeviceTokenSerializer, OrderSerializer, StatusChangeSerializer
from .services import update_order_status


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = (IsAuthenticated, CanAccessOrder)
    filterset_fields = ("status",)

    def get_queryset(self):
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

    def create(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        DeviceToken.objects.update_or_create(token=serializer.validated_data["token"], defaults={"user": request.user, "platform": serializer.validated_data["platform"], "active": True})
        return Response(status=status.HTTP_204_NO_CONTENT)


class InternalNotificationDeliveryViewSet(viewsets.ViewSet):
    """Callback used only by the SQS-triggered Lambda after a provider attempt."""
    authentication_classes = ()
    permission_classes = ()

    def create(self, request, job_id=None):
        if not settings.INTERNAL_NOTIFICATION_SECRET or request.headers.get("X-Internal-Secret") != settings.INTERNAL_NOTIFICATION_SECRET:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        job = NotificationJob.objects.get(pk=job_id)
        state = request.data.get("state")
        if state not in (NotificationJob.State.SENT, NotificationJob.State.FAILED):
            return Response({"detail": "Invalid notification state."}, status=status.HTTP_400_BAD_REQUEST)
        job.state = state
        job.provider_message_id = request.data.get("provider_message_id", "")
        job.failure_reason = request.data.get("failure_reason", "")
        job.save(update_fields=["state", "provider_message_id", "failure_reason"])
        return Response(status=status.HTTP_204_NO_CONTENT)
