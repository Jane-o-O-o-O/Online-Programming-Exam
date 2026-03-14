from celery import shared_task


@shared_task
def ping_judge() -> str:
    return "judge worker is alive"
