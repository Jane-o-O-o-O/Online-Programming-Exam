from functools import wraps

from django.http import JsonResponse

from .models import User


MANAGER_ROLES = {User.Role.ADMIN, User.Role.TEACHER}


def json_auth_error(message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def login_required_json(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_auth_error("authentication required", 401)
        return view_func(request, *args, **kwargs)

    return wrapped


def role_required(*roles):
    allowed_roles = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        @login_required_json
        def wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or getattr(user, "role", None) in allowed_roles:
                return view_func(request, *args, **kwargs)
            return json_auth_error("permission denied", 403)

        return wrapped

    return decorator


def user_can_manage_exams(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or getattr(user, "role", None) in MANAGER_ROLES))
