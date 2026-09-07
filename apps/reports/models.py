import uuid

from django.db import models


class AIReport(models.Model):
    """Stores the daily AI-generated sales summary so the admin dashboard can display it without recomputing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_date = models.DateField(unique=True)
    summary_text = models.TextField()
    raw_data = models.JSONField(help_text="The aggregates that were sent to the AI model")
    model_used = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_reports"
        ordering = ["-report_date"]

    def __str__(self):
        return f"AI sales report — {self.report_date}"
