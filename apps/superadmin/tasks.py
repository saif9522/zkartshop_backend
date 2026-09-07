import logging
import shutil
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(settings.BASE_DIR) / "backups"


@shared_task
def run_database_backup(backup_log_id):
    """
    Backs up the configured database to BACKUP_DIR.
    - SQLite (the default): copies the db file directly.
    - PostgreSQL (DB_ENGINE=postgresql): runs `pg_dump`.
    In production, swap the local save for an upload to S3/R2
    (django-storages is already configured — see settings/production.py).
    """
    from apps.superadmin.models import BackupLog

    log = BackupLog.objects.get(id=backup_log_id)
    BACKUP_DIR.mkdir(exist_ok=True)

    db = settings.DATABASES["default"]
    is_sqlite = db["ENGINE"].endswith("sqlite3")

    try:
        if is_sqlite:
            filename = f"mall_of_garhwa_{timezone.now():%Y%m%d_%H%M%S}.sqlite3"
            filepath = BACKUP_DIR / filename
            shutil.copy(db["NAME"], filepath)
        else:
            filename = f"mall_of_garhwa_{timezone.now():%Y%m%d_%H%M%S}.sql"
            filepath = BACKUP_DIR / filename
            env = {"PGPASSWORD": db["PASSWORD"]}
            cmd = [
                "pg_dump",
                "-h", db["HOST"] or "localhost",
                "-p", str(db["PORT"] or 5432),
                "-U", db["USER"],
                "-f", str(filepath),
                db["NAME"],
            ]
            subprocess.run(cmd, env=env, check=True, capture_output=True, text=True, timeout=300)

        log.filename = filename
        log.size_bytes = filepath.stat().st_size
        log.status = BackupLog.Status.SUCCESS
    except Exception as exc:
        logger.error("Database backup failed: %s", exc)
        log.status = BackupLog.Status.FAILED
        log.error_message = str(exc)[:2000]
    finally:
        log.finished_at = timezone.now()
        log.save(update_fields=["filename", "size_bytes", "status", "error_message", "finished_at"])

    return {"status": log.status, "filename": log.filename}
