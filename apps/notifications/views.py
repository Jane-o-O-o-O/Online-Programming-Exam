from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.permissions import login_required_json

from .models import Notification


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "category": notification.category,
        "title": notification.title,
        "content": notification.content,
        "recipient": notification.recipient,
        "status": notification.status,
        "error_message": notification.error_message,
        "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


@require_GET
@login_required_json
def summary(request: HttpRequest) -> JsonResponse:
    queryset = Notification.objects.filter(user=request.user)
    return JsonResponse(
        {
            "total": queryset.count(),
            "unread": queryset.filter(is_read=False).count(),
            "pending": queryset.filter(status=Notification.Status.PENDING).count(),
            "sent": queryset.filter(status=Notification.Status.SENT).count(),
            "failed": queryset.filter(status=Notification.Status.FAILED).count(),
        }
    )


@require_GET
@login_required_json
def notifications(request: HttpRequest) -> JsonResponse:
    queryset = Notification.objects.filter(user=request.user).order_by("-created_at", "-id")
    category = request.GET.get("category")
    status = request.GET.get("status")
    is_read = request.GET.get("is_read")

    if category:
        queryset = queryset.filter(category=category)
    if status:
        queryset = queryset.filter(status=status)
    if is_read in {"true", "false"}:
        queryset = queryset.filter(is_read=is_read == "true")

    return JsonResponse({"results": [serialize_notification(item) for item in queryset]})


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def mark_read(request: HttpRequest, notification_id: int) -> JsonResponse:
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.mark_read()
    return JsonResponse({"notification": serialize_notification(notification)})


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def mark_all_read(request: HttpRequest) -> JsonResponse:
    now = timezone.now()
    count = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=now)
    return JsonResponse({"marked": count})
