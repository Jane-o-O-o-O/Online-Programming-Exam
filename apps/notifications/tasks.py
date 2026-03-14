from celery import shared_task


@shared_task
def send_mock_email(subject: str, recipient: str) -> str:
    return f"queued: {subject} -> {recipient}"
