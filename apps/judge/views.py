from django.http import JsonResponse

from .models import JudgeTask


def queue_status(_request):
    return JsonResponse(
        {
            "queued": JudgeTask.objects.filter(status=JudgeTask.Status.QUEUED).count(),
            "running": JudgeTask.objects.filter(status=JudgeTask.Status.RUNNING).count(),
            "finished": JudgeTask.objects.filter(status__in=[JudgeTask.Status.SUCCESS, JudgeTask.Status.FAILED]).count(),
        }
    )
