from django.http import JsonResponse

from .models import User


def stats(_request):
    return JsonResponse(
        {
            "users": User.objects.count(),
            "teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "students": User.objects.filter(role=User.Role.STUDENT).count(),
        }
    )
