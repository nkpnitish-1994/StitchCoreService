from rest_framework.permissions import BasePermission
from .models import User


class IsOpsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_ops_admin)


class CanAccessOrder(BasePermission):
    def has_object_permission(self, request, view, order):
        user = request.user
        return user.is_ops_admin or order.customer_id == user.id or order.logistics_partner_id == user.id


def is_logistics(user):
    return user.role == User.Role.LOGISTICS

