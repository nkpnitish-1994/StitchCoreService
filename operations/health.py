from django.db import connection
from django.http import JsonResponse


def health(request):
    """Readiness for the load balancer; never disclose database errors."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
