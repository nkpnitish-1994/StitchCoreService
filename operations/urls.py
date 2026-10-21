from rest_framework.routers import DefaultRouter
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import CurrentUserView, OperationsOptionsView
from .views import AddressViewSet, DeviceTokenViewSet, InternalNotificationDeliveryViewSet, OrderViewSet, OtpRequestView, OtpVerifyView, QuoteView, ServiceListView, BetaSessionView, AuthConfigurationView

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("orders", OrderViewSet, basename="order")
router.register("device-tokens", DeviceTokenViewSet, basename="device-token")

urlpatterns = [
    path("auth/me", CurrentUserView.as_view()),
    path("auth/token/refresh", TokenRefreshView.as_view()),
    path("operations/options", OperationsOptionsView.as_view()),
    *router.urls,
    path("auth/beta/session", BetaSessionView.as_view()),
    path("auth/config", AuthConfigurationView.as_view()),
    path("auth/otp/request", OtpRequestView.as_view()),
    path("auth/otp/verify", OtpVerifyView.as_view()),
    path("catalog/services", ServiceListView.as_view()),
    path("orders/quote", QuoteView.as_view()),
    path("internal/notifications/<uuid:job_id>/delivery/", InternalNotificationDeliveryViewSet.as_view({"post": "create"})),
]
