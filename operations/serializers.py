from rest_framework import serializers
from .models import Address, AlterationItem, DeviceToken, Garment, Order, StatusEvent, Vendor


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ("id", "label", "line1", "line2", "city", "postal_code", "landmark", "latitude", "longitude")
        read_only_fields = ("id",)


class AlterationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlterationItem
        fields = ("id", "service_code", "measurement_data", "notes", "quoted_price_paise", "approved_price_paise")
        read_only_fields = ("id", "approved_price_paise")


class GarmentSerializer(serializers.ModelSerializer):
    alterations = AlterationItemSerializer(many=True)

    class Meta:
        model = Garment
        fields = ("id", "garment_type", "colour", "quantity", "qr_code", "pickup_photo_url", "condition_notes", "alterations")
        read_only_fields = ("id", "qr_code")


class StatusEventSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source="changed_by.get_full_name", read_only=True)

    class Meta:
        model = StatusEvent
        fields = ("id", "from_status", "to_status", "changed_by_name", "note", "proof_url", "created_at")


class OrderSerializer(serializers.ModelSerializer):
    garments = GarmentSerializer(many=True)
    address = AddressSerializer(read_only=True)
    status_events = StatusEventSerializer(many=True, read_only=True)
    total_paise = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "order_number", "status", "pickup_window", "expected_delivery_date",
            "subtotal_paise", "delivery_fee_paise", "total_paise", "address", "garments",
            "status_events", "logistics_partner_id", "vendor_id", "created_at", "updated_at",
        )
        read_only_fields = ("id", "order_number", "status", "subtotal_paise", "delivery_fee_paise", "total_paise", "logistics_partner_id", "vendor_id", "created_at", "updated_at")


class CreateOrderSerializer(serializers.Serializer):
    address_id = serializers.PrimaryKeyRelatedField(source="address", queryset=Address.objects.all())
    pickup_window = serializers.CharField(max_length=100)
    expected_delivery_date = serializers.DateField(required=False, allow_null=True)
    garments = GarmentSerializer(many=True, min_length=1)

    def validate_address(self, address):
        if address.user_id != self.context["request"].user.id:
            raise serializers.ValidationError("Choose one of your saved addresses.")
        return address

    def create(self, validated_data):
        garments = validated_data.pop("garments")
        subtotal = sum(
            item["quoted_price_paise"] * garment.get("quantity", 1)
            for garment in garments for item in garment["alterations"]
        )
        order = Order.objects.create(customer=self.context["request"].user, subtotal_paise=subtotal, **validated_data)
        for garment_data in garments:
            alterations = garment_data.pop("alterations")
            garment = Garment.objects.create(order=order, **garment_data)
            for alteration in alterations:
                AlterationItem.objects.create(garment=garment, **alteration)
        StatusEvent.objects.create(order=order, from_status="", to_status=Order.Status.PLACED, changed_by=order.customer, note="Order placed")
        return order


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    proof_url = serializers.URLField(required=False, allow_blank=True)


class AssignmentSerializer(serializers.Serializer):
    logistics_partner_id = serializers.PrimaryKeyRelatedField(queryset=__import__("operations.models", fromlist=["User"]).User.objects.all(), required=False)
    vendor_id = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False)

    def validate(self, data):
        partner = data.get("logistics_partner_id")
        if partner and partner.role != "logistics":
            raise serializers.ValidationError({"logistics_partner_id": "Selected user is not a logistics partner."})
        return data


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("platform", "token")

