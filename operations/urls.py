from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import AddressViewSet, DeviceTokenViewSet, InternalNotificationDeliveryViewSet, OrderViewSet, OtpRequestView, OtpVerifyView, QuoteView, ServiceListView

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("orders", OrderViewSet, basename="order")
router.register("device-tokens", DeviceTokenViewSet, basename="device-token")

urlpatterns = [
    *router.urls,
    path("auth/otp/request", OtpRequestView.as_view()),
    path("auth/otp/verify", OtpVerifyView.as_view()),
    path("catalog/services", ServiceListView.as_view()),
    path("orders/quote", QuoteView.as_view()),
    path("internal/notifications/<uuid:job_id>/delivery/", InternalNotificationDeliveryViewSet.as_view({"post": "create"})),
]
