from typing import Any

from config.celery import app


@app.task  # type: ignore[untyped-decorator]
def notify_status_change(payload: dict[str, Any]) -> None:
    """
    Async task to handle pet status change notifications.
    """
