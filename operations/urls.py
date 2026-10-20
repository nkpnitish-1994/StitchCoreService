from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import AddressViewSet, DeviceTokenViewSet, InternalNotificationDeliveryViewSet, OrderViewSet

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("orders", OrderViewSet, basename="order")
router.register("device-tokens", DeviceTokenViewSet, basename="device-token")

urlpatterns = [
    *router.urls,
    path("internal/notifications/<uuid:job_id>/delivery/", InternalNotificationDeliveryViewSet.as_view({"post": "create"})),
]
