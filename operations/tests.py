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


class ApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user("contract-customer", role=User.Role.CUSTOMER)

    def test_versioned_routes_and_legacy_routes(self):
        from django.urls import Resolver404, resolve
        for route in ("addresses/", "orders/", "device-tokens/", "auth/otp/request",
                      "auth/otp/verify", "catalog/services", "orders/quote",
                      "internal/notifications/00000000-0000-0000-0000-000000000001/delivery/"):
            with self.subTest(route=route):
                resolve(f"/api/v1/{route}")
                with self.assertRaises(Resolver404):
                    resolve(f"/api/{route}")
        self.assertEqual(self.client.get("/api/v1/catalog/services").status_code, 200)

    def test_authentication_error(self):
        response = self.client.get("/api/v1/orders/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["code"], "not_authenticated")
        self.assertEqual(response.data["fields"], {})
        self.assertIsInstance(response.data["message"], str)

    def test_validation_error_preserves_field_details(self):
        response = self.client.post("/api/v1/auth/otp/request", {"phone": "bad"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("phone", response.data["fields"])

    def test_missing_object_and_method_errors(self):
        self.client.force_authenticate(self.customer)
        for url, method, expected_status, code in [
            ("/api/v1/orders/999999/", "get", 404, "not_found"),
            ("/api/v1/auth/otp/request", "get", 405, "method_not_allowed"),
        ]:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.data["code"], code)

    def test_permission_and_transition_errors(self):
        address = Address.objects.create(user=self.customer, line1="Test", city="Test", postal_code="560001")
        order = Order.objects.create(customer=self.customer, address=address, pickup_window="17:00")
        self.client.force_authenticate(self.customer)
        response = self.client.post(f"/api/v1/orders/{order.pk}/status/", {"status": "delivered"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "permission_denied")
        admin = User.objects.create_user("contract-admin", role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        response = self.client.post(f"/api/v1/orders/{order.pk}/status/", {"status": "delivered"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_status_transition")
        order.refresh_from_db()
        self.assertEqual(order.status, "placed")
        self.assertFalse(order.status_events.exists())

    def test_internal_callback_is_versioned_and_protected(self):
        url = "/api/v1/internal/notifications/00000000-0000-0000-0000-000000000001/delivery/"
        response = self.client.post(url, {"state": "sent"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "not_found")
        with self.settings(INTERNAL_NOTIFICATION_SECRET="test-only-secret"):
            response = self.client.post(url, {"state": "sent"}, HTTP_X_INTERNAL_SECRET="test-only-secret")
        self.assertEqual(response.status_code, 404)

    def test_generated_schema_matches_committed_contract(self):
        from pathlib import Path
        import yaml
        from django.conf import settings
        from drf_spectacular.generators import SchemaGenerator
        from drf_spectacular.validation import validate_schema
        schema = SchemaGenerator().get_schema(request=None, public=True)
        validate_schema(schema)
        committed = yaml.safe_load((Path(settings.BASE_DIR) / "packages/contracts/openapi.yaml").read_text())
        self.assertEqual(schema, committed, "Run make openapi and commit the regenerated contract.")
        self.assertTrue(all(path.startswith("/api/v1/") for path in schema["paths"]))
        operation = schema["paths"]["/api/v1/orders/"]["post"]
        self.assertEqual(operation["responses"]["201"]["content"]["application/json"]["schema"],
                         {"$ref": "#/components/schemas/Order"})
        self.assertIn("204", schema["paths"]["/api/v1/device-tokens/"]["post"]["responses"])

    def test_schema_and_documentation_are_available(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/v1/orders/", response.data["paths"])
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)

    def test_lambda_reports_to_versioned_internal_callback(self):
        import os
        import runpy
        from pathlib import Path
        from unittest.mock import patch
        from django.conf import settings
        with patch.dict(os.environ, {
            "INTERNAL_API_BASE_URL": "https://api.example.test",
            "INTERNAL_NOTIFICATION_SECRET": "test-only-secret",
        }):
            adapter = runpy.run_path(str(Path(settings.BASE_DIR) / "infra/lambda/notifications/handler.py"))
        with patch("urllib.request.urlopen") as send:
            send.return_value.__enter__.return_value.status = 204
            adapter["report"]("00000000-0000-0000-0000-000000000001", "sent")
        request = send.call_args.args[0]
        self.assertEqual(request.full_url,
                         "https://api.example.test/api/v1/internal/notifications/"
                         "00000000-0000-0000-0000-000000000001/delivery/")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(send.call_args.kwargs["timeout"], 8)
