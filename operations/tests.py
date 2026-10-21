from django.test import TestCase
from rest_framework.test import APIClient
from .models import Address, Order, Service, User


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("customer", password="password", role=User.Role.CUSTOMER)
        self.logistics = User.objects.create_user("rider", password="password", role=User.Role.LOGISTICS)
        self.admin = User.objects.create_user("admin", password="password", role=User.Role.ADMIN)
        self.address = Address.objects.create(user=self.customer, line1="10 Market Road", city="Bengaluru", postal_code="560001")
        Service.objects.create(code="reduce_waist", name="Reduce waist", garment_type="trousers", base_price_paise=19900)

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


class DeploymentReadinessTests(TestCase):
    def test_health_checks_database_without_disclosing_failures(self):
        from unittest.mock import patch
        client = APIClient()
        self.assertEqual(client.get("/health/").json(), {"status": "ok"})
        with patch("operations.health.connection.cursor", side_effect=RuntimeError("private database details")):
            response = client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_unconfigured_otp_does_not_claim_a_code_was_sent(self):
        from .models import OtpChallenge
        with self.settings(DEBUG=False, OTP_PROVIDER="disabled"):
            response = APIClient().post("/api/v1/auth/otp/request", {"phone": "+919900000099"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "provider_unavailable")
        self.assertFalse(OtpChallenge.objects.exists())

    def test_notification_adapter_cannot_falsely_report_delivery(self):
        import os
        import runpy
        from pathlib import Path
        from unittest.mock import patch
        from django.conf import settings
        with patch.dict(os.environ, {"INTERNAL_API_BASE_URL": "https://api.example.test"}):
            adapter = runpy.run_path(str(Path(settings.BASE_DIR) / "infra/lambda/notifications/handler.py"))
        with self.assertRaises(NotImplementedError):
            adapter["deliver"]({"notification_job_id": "test", "channel": "push"})

    def test_migration_lock_is_released_after_failure(self):
        from unittest.mock import MagicMock, patch
        from .management.commands.migrate_locked import Command
        database = MagicMock(vendor="postgresql")
        with patch("operations.management.commands.migrate_locked.connection", database), patch(
            "operations.management.commands.migrate_locked.call_command", side_effect=RuntimeError("migration failed")
        ):
            with self.assertRaises(RuntimeError):
                Command().handle()
        calls = database.cursor.return_value.__enter__.return_value.execute.call_args_list
        self.assertEqual(calls[0].args, ("SELECT pg_advisory_lock(784326951)",))
        self.assertEqual(calls[1].args, ("SELECT pg_advisory_unlock(784326951)",))


class BetaJourneyTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user("beta-customer", password="test-password", role="customer")
        self.address = Address.objects.create(user=self.user, line1="Beta test address", city="Test", postal_code="560001")
        Service.objects.create(code="trousers.reduce_waist", name="Reduce waist", garment_type="trousers", base_price_paise=19900)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.payload = {"address_id": self.address.pk, "pickup_window": "17:00-20:00", "garments": [
            {"garment_type": "trousers", "quantity": 2, "colour": "Navy", "alterations": [
                {"service_code": "trousers.reduce_waist", "quoted_price_paise": 1,
                 "measurement_data": {"measurement_mode": "pickup_measurement"}}]}]}

    def test_price_is_server_calculated_and_retries_do_not_duplicate_order(self):
        import uuid
        key = str(uuid.uuid4())
        first = self.client.post("/api/v1/orders/", self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["total_paise"], 39800)
        second = self.client.post("/api/v1/orders/", self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().status_events.count(), 1)
        self.assertEqual(Order.objects.get().garments.get().alterations.get().service_name_snapshot, "Reduce waist")

    def test_reused_key_with_different_content_is_rejected(self):
        import uuid
        key = str(uuid.uuid4())
        self.client.post("/api/v1/orders/", self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.payload["pickup_window"] = "Changed pickup"
        response = self.client.post("/api/v1/orders/", self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 1)

    def test_unsupported_service_and_other_customers_address_rejected(self):
        other = User.objects.create_user("other-beta")
        self.address.user = other
        self.address.save()
        response = self.client.post("/api/v1/orders/", self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.address.user = self.user
        self.address.save()
        self.payload["garments"][0]["alterations"][0]["service_code"] = "unpriced"
        response = self.client.post("/api/v1/orders/", self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_order_cannot_be_deleted_or_patched(self):
        created = self.client.post("/api/v1/orders/", self.payload, format="json")
        url = f"/api/v1/orders/{created.data['id']}/"
        self.assertEqual(self.client.patch(url, {"status": "delivered"}).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertEqual(Order.objects.count(), 1)

    def test_beta_sign_in_is_gated_and_authenticates_real_test_accounts(self):
        client = APIClient()
        with self.settings(BETA_AUTH_ENABLED=True, STITCHCORE_ENV="production"):
            self.assertEqual(client.post("/api/v1/auth/beta/session", {"username": "beta-customer", "password": "test-password"}).status_code, 404)
            self.assertFalse(client.get("/api/v1/auth/config").data["beta_sign_in"])
        with self.settings(BETA_AUTH_ENABLED=True, STITCHCORE_ENV="beta"):
            self.assertTrue(client.get("/api/v1/auth/config").data["beta_sign_in"])
            response = client.post("/api/v1/auth/beta/session", {"username": "beta-customer", "password": "wrong"})
            self.assertEqual(response.status_code, 401)
            response = client.post("/api/v1/auth/beta/session", {"username": "beta-customer", "password": "test-password"})
            self.assertEqual(response.status_code, 200)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
            self.assertEqual(client.get("/api/v1/addresses/").data[0]["id"], self.address.pk)

    def test_beta_login_throttles(self):
        client = APIClient()
        with self.settings(BETA_AUTH_ENABLED=True, STITCHCORE_ENV="beta"):
            for _ in range(5):
                self.assertEqual(client.post("/api/v1/auth/beta/session", {"username": "beta-customer", "password": "wrong"}).status_code, 401)
            self.assertEqual(client.post("/api/v1/auth/beta/session", {"username": "beta-customer", "password": "wrong"}).status_code, 429)

    def test_beta_preparation_is_idempotent_and_rejects_production(self):
        import os
        from unittest.mock import patch
        from django.core.management import call_command, CommandError
        with self.settings(STITCHCORE_ENV="production"):
            with self.assertRaises(CommandError):
                call_command("prepare_beta")
        with self.settings(STITCHCORE_ENV="beta"), patch.dict(os.environ, {
            "BETA_ADMIN_PASSWORD": "test-admin-password",
            "BETA_CUSTOMER_PASSWORD": "test-customer-password",
        }), patch("operations.management.commands.prepare_beta.call_command"):
            call_command("prepare_beta")
            call_command("prepare_beta")
        self.assertEqual(User.objects.filter(username="beta-admin").count(), 1)
        self.assertTrue(User.objects.get(username="beta-admin").is_superuser)
        self.assertTrue(User.objects.get(username="beta-customer").check_password("test-customer-password"))


class OperationsJourneyTests(TestCase):
    setUp = BetaJourneyTests.setUp
    def test_admin_assigns_and_completes_order_with_customer_timeline(self):
        from .models import Vendor
        created = self.client.post("/api/v1/orders/", self.payload, format="json")
        order_id = created.data["id"]
        admin = User.objects.create_user("ops-admin", role="admin")
        partner = User.objects.create_user("ops-partner", role="logistics")
        vendor = Vendor.objects.create(name="Test vendor", phone="", address="Test")
        self.assertEqual(self.client.get("/api/v1/operations/options").status_code, 403)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/v1/operations/options").status_code, 200)
        assigned = self.client.post(f"/api/v1/orders/{order_id}/assign/", {
            "logistics_partner_id": partner.pk, "vendor_id": vendor.pk,
        }, format="json")
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.data["status"], "pickup_assigned")
        for step in ("picked_up", "at_vendor", "alteration_complete", "ready_for_delivery", "out_for_delivery", "delivered"):
            response = self.client.post(f"/api/v1/orders/{order_id}/status/", {"status": step, "note": "Synthetic beta verification"})
            self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.user)
        detail = self.client.get(f"/api/v1/orders/{order_id}/")
        self.assertEqual(detail.data["status"], "delivered")
        self.assertEqual(len(detail.data["status_events"]), 9)
        stranger = User.objects.create_user("stranger")
        self.client.force_authenticate(stranger)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order_id}/").status_code, 404)

    def test_logistics_cannot_approve_vendor_work_or_reassign(self):
        partner = User.objects.create_user("limited-partner", role="logistics")
        other_partner = User.objects.create_user("unassigned-partner", role="logistics")
        order = Order.objects.create(customer=self.user, address=self.address, pickup_window="Test", status="at_vendor", logistics_partner=partner)
        self.client.force_authenticate(partner)
        self.assertEqual(self.client.post(f"/api/v1/orders/{order.pk}/status/", {"status": "alteration_complete"}).status_code, 403)
        order.status = "customer_approval_needed"
        order.save(update_fields=["status"])
        self.assertEqual(self.client.post(f"/api/v1/orders/{order.pk}/status/", {"status": "at_vendor"}).status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/orders/{order.pk}/assign/", {"logistics_partner_id": other_partner.pk}).status_code, 403)
        self.client.force_authenticate(other_partner)
        self.assertEqual(self.client.get(f"/api/v1/orders/{order.pk}/").status_code, 404)

    def test_stale_state_cannot_overwrite_a_recorded_transition(self):
        from .services import update_order_status
        admin = User.objects.create_user("concurrency-admin", role="admin")
        order = Order.objects.create(customer=self.user, address=self.address, pickup_window="Test")
        stale = Order.objects.get(pk=order.pk)
        update_order_status(order=order, actor=admin, to_status="cancelled")
        with self.assertRaises(ValueError):
            update_order_status(order=stale, actor=admin, to_status="pickup_assigned")
        self.assertEqual(Order.objects.get(pk=order.pk).status, "cancelled")

    def test_queue_failure_preserves_status_and_pending_job(self):
        from unittest.mock import patch
        from .models import NotificationJob
        from .services import update_order_status
        admin = User.objects.create_user("queue-admin", role="admin")
        order = Order.objects.create(customer=self.user, address=self.address, pickup_window="Test")
        with self.settings(NOTIFICATION_QUEUE_URL="https://queue.test"), patch("operations.services.boto3.client", side_effect=RuntimeError("queue down")), self.assertLogs("operations.services", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                update_order_status(order=order, actor=admin, to_status="cancelled")
        self.assertEqual(Order.objects.get(pk=order.pk).status, "cancelled")
        self.assertEqual(NotificationJob.objects.filter(order=order, state="pending").count(), 2)
