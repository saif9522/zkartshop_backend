"""
Celery app for zKart.shop.

Run a worker:      celery -A mall_of_garhwa worker -l info
Run the scheduler:  celery -A mall_of_garhwa beat -l info
(Both need Redis running, and both read CELERY_* settings from Django.)
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mall_of_garhwa.settings.development")

app = Celery("mall_of_garhwa")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# ---------------------------------------------------------------------------
# Periodic jobs (Celery Beat). Add new recurring tasks here.
# ---------------------------------------------------------------------------
app.conf.beat_schedule = {
    "auto-cancel-unaccepted-orders": {
        "task": "apps.orders.tasks.auto_cancel_stale_orders",
        "schedule": crontab(minute="*/2"),  # every 2 minutes
    },
    "check-inventory-expiry": {
        "task": "apps.inventory.tasks.check_expiring_stock",
        "schedule": crontab(hour=6, minute=0),  # once a day, 6 AM IST
    },
    "generate-daily-sales-report": {
        "task": "apps.reports.tasks.generate_daily_ai_sales_report",
        "schedule": crontab(hour=23, minute=45),  # end of day
    },
    "dispatch-scheduled-campaigns": {
        "task": "apps.marketing.tasks.send_scheduled_campaigns",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
}

app.conf.timezone = "Asia/Kolkata"


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
