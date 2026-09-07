from django.contrib import admin

from apps.reports.models import AIReport


@admin.register(AIReport)
class AIReportAdmin(admin.ModelAdmin):
    list_display = ["report_date", "model_used", "created_at"]
    readonly_fields = ["created_at"]
