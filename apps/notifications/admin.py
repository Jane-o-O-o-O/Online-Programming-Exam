from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "recipient", "status", "sent_at", "created_at")
    list_filter = ("category", "status")
    search_fields = ("title", "recipient", "content")
