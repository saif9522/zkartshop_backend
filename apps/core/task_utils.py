import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

logger = logging.getLogger(__name__)

# Shared pool for bounding any "best-effort, must not block the request" side
# effect — Celery task queuing, WebSocket broadcasts, etc. These are all
# fire-and-forget, so a handful of workers is plenty even under a burst.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-sideeffect")


def run_with_timeout(func, *args, timeout=0.5, **kwargs):
    """
    Runs func(*args, **kwargs) in a worker thread with a hard timeout, so
    the caller is guaranteed to get control back within ~`timeout` seconds
    regardless of what's slow inside (broker connection retries, DNS,
    Redis being down entirely, etc.). If it doesn't finish in time, the
    background thread is left to finish or fail on its own — the caller
    just stops waiting for it.

    Returns True if func completed without raising, False otherwise
    (timeout or exception — always logged as a warning, never re-raised).
    """
    future = _executor.submit(func, *args, **kwargs)
    try:
        future.result(timeout=timeout)
        return True
    except FutureTimeoutError:
        logger.warning("%s did not complete within %.1fs — continuing without it.", getattr(func, "__name__", func), timeout)
        return False
    except Exception as exc:
        logger.warning("%s failed (%s) — continuing without it.", getattr(func, "__name__", func), exc)
        return False


def safe_delay(task, *args, timeout=0.5, **kwargs):
    """
    Queues a Celery task via .delay(), but never lets a broker outage
    (Redis down, unreachable, etc.) break the calling request. Used for
    best-effort side effects — SMS/push notifications, broadcasts — where
    the primary operation (checkout, OTP send, status change) must succeed
    even if the notification can't be queued right now.

    Returns True if the task was queued, False if it failed or timed out.
    """
    return run_with_timeout(task.delay, *args, timeout=timeout, **kwargs)
