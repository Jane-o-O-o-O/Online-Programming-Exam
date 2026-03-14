from django.http import JsonResponse

from .models import Notification


def summary(_request):
    return JsonResponse(
        {
            "total": Notification.objects.count(),
            "pending": Notification.objects.filter(status=Notification.Status.PENDING).count(),
            "sent": Notification.objects.filter(status=Notification.Status.SENT).count(),
        }
    )
