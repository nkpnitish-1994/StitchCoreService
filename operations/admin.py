from django.contrib import admin
from .models import Address, AlterationItem, DeviceToken, Garment, NotificationJob, Order, StatusEvent, User, Vendor


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "phone", "role", "is_active")
    list_filter = ("role", "is_active")


class GarmentInline(admin.TabularInline):
    model = Garment
    extra = 0


class StatusEventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "proof_url", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    readonly_fields = ("status", "logistics_partner", "vendor", "subtotal_paise", "delivery_fee_paise", "discount_paise", "idempotency_key")
    list_display = ("order_number", "customer", "status", "logistics_partner", "vendor", "created_at")
    list_filter = ("status", "vendor")
    search_fields = ("order_number", "customer__phone", "customer__username")
    inlines = (GarmentInline, StatusEventInline)


admin.site.register((Address, Vendor, AlterationItem, NotificationJob, DeviceToken))

