from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.permissions import login_required_json, role_required
from apps.accounts.models import User

from .models import JudgeTask
from .services import retry_judge_task


def serialize_task(task: JudgeTask) -> dict:
    answer = task.answer
    submission = answer.submission
    return {
        "id": task.id,
        "status": task.status,
        "language": task.language,
        "docker_image": task.docker_image,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "result_payload": task.result_payload,
        "answer": {
            "id": answer.id,
            "judge_status": answer.judge_status,
            "auto_score": float(answer.auto_score),
            "question_id": answer.question_id,
            "submission_id": submission.id,
            "exam_id": submission.exam_id,
            "student_id": submission.student_id,
        },
    }


@require_GET
@login_required_json
def queue_status(request: HttpRequest) -> JsonResponse:
    queryset = JudgeTask.objects.all()
    return JsonResponse(
        {
            "queued": queryset.filter(status=JudgeTask.Status.QUEUED).count(),
            "running": queryset.filter(status=JudgeTask.Status.RUNNING).count(),
            "finished": queryset.filter(status__in=[JudgeTask.Status.SUCCESS, JudgeTask.Status.FAILED]).count(),
        }
    )


@require_GET
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def task_list(_request: HttpRequest) -> JsonResponse:
    queryset = JudgeTask.objects.select_related("answer__submission", "answer__question").order_by("-id")
    return JsonResponse({"results": [serialize_task(item) for item in queryset]})


@csrf_exempt
@require_http_methods(["POST"])
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def retry_task(_request: HttpRequest, task_id: int) -> JsonResponse:
    task = get_object_or_404(JudgeTask.objects.select_related("answer__submission__exam", "answer__question"), pk=task_id)
    task = retry_judge_task(task)
    return JsonResponse({"task": serialize_task(task)})
