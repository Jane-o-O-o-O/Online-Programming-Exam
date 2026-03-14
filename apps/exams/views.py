from django.http import JsonResponse

from .models import Exam, Question, Submission


def overview(_request):
    return JsonResponse(
        {
            "exam_count": Exam.objects.count(),
            "question_count": Question.objects.count(),
            "submission_count": Submission.objects.count(),
        }
    )
