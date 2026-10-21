from django.test import TestCase
from rest_framework.test import APIClient
from .models import Address, Order, Service, User


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("customer", password="password", role=User.Role.CUSTOMER)
        self.logistics = User.objects.create_user("rider", password="password", role=User.Role.LOGISTICS)
        self.admin = User.objects.create_user("admin", password="password", role=User.Role.ADMIN)
        self.address = Address.objects.create(user=self.customer, line1="10 Market Road", city="Bengaluru", postal_code="560001")

    def test_customer_can_create_order_and_logistics_can_update_assigned_order(self):
        client = APIClient()
        client.force_authenticate(self.customer)
        response = client.post("/api/v1/orders/", {
            "address_id": self.address.id,
            "pickup_window": "17:00-20:00",
            "garments": [{"garment_type": "trousers", "colour": "Navy", "quantity": 1, "alterations": [{"service_code": "reduce_waist", "measurement_data": {"inches": 1}, "quoted_price_paise": 19900}]}],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        order.logistics_partner = self.logistics
        order.status = Order.Status.PICKUP_ASSIGNED
        order.save()

        client.force_authenticate(self.logistics)
        response = client.post(f"/api/v1/orders/{order.id}/status/", {"status": "picked_up", "note": "One garment scanned"}, format="json")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PICKED_UP)

    def test_otp_login_and_quote(self):
        Service.objects.create(code="trousers.reduce_waist", name="Reduce waist", garment_type="trousers", base_price_paise=19900, measurement_schema={"schema_version": 1})
        client = APIClient()
        with self.settings(DEBUG=True, OTP_PROVIDER="console"):
            response = client.post("/api/v1/auth/otp/request", {"phone": "+919900000099"}, format="json")
        self.assertEqual(response.status_code, 202)
        # OTP verification hashing is covered by the model; inject the known challenge code to keep API test deterministic.
        from .models import OtpChallenge
        challenge = OtpChallenge.objects.get(phone="+919900000099")
        challenge.code_hash = __import__("django.contrib.auth.hashers", fromlist=["make_password"]).make_password("123456")
        challenge.save(update_fields=["code_hash"])
        response = client.post("/api/v1/auth/otp/verify", {"phone": "+919900000099", "code": "123456"}, format="json")
        self.assertEqual(response.status_code, 200)
        token = response.data["access"]
        customer = User.objects.get(phone="+919900000099")
        address = Address.objects.create(user=customer, line1="10 Market Road", city="Bengaluru", postal_code="560001")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.post("/api/v1/orders/quote", {"address_id": address.id, "garments": [{"garment_type": "trousers", "quantity": 1, "alterations": [{"service_code": "trousers.reduce_waist", "measurement": {"schema_version": 1, "measurement_mode": "alteration_delta", "unit": "in", "values": {"waist_reduce_by": 1}}}]}]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_paise"], 19900)
