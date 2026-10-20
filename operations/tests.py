from django.test import TestCase
from rest_framework.test import APIClient
from .models import Address, Order, User


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("customer", password="password", role=User.Role.CUSTOMER)
        self.logistics = User.objects.create_user("rider", password="password", role=User.Role.LOGISTICS)
        self.admin = User.objects.create_user("admin", password="password", role=User.Role.ADMIN)
        self.address = Address.objects.create(user=self.customer, line1="10 Market Road", city="Bengaluru", postal_code="560001")

    def test_customer_can_create_order_and_logistics_can_update_assigned_order(self):
        client = APIClient()
        client.force_authenticate(self.customer)
        response = client.post("/api/orders/", {
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
        response = client.post(f"/api/orders/{order.id}/status/", {"status": "picked_up", "note": "One garment scanned"}, format="json")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PICKED_UP)

