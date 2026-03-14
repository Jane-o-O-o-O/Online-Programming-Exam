import json

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.notifications.services import (
    clear_password_reset_state,
    get_password_reset_state,
    increment_password_reset_attempts,
    send_password_reset_code,
)

from .models import User
from .permissions import login_required_json, role_required


def parse_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("request body must be valid JSON")



def json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)



def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "real_name": user.real_name,
        "mobile": user.mobile,
        "is_staff": user.is_staff,
    }


@require_GET
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def stats(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "users": User.objects.count(),
            "teachers": User.objects.filter(role=User.Role.TEACHER).count(),
            "students": User.objects.filter(role=User.Role.STUDENT).count(),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def register(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    email = (payload.get("email") or "").strip().lower()
    role = payload.get("role") or User.Role.STUDENT

    if not username or not password or not email:
        return json_error("username, password and email are required")
    if len(password) < 6:
        return json_error("password must be at least 6 characters")
    if role not in {User.Role.STUDENT, User.Role.TEACHER}:
        return json_error("only student or teacher can be self-registered")
    if User.objects.filter(username=username).exists():
        return json_error("username already exists", 409)
    if User.objects.filter(email=email).exists():
        return json_error("email already exists", 409)

    user = User.objects.create_user(
        username=username,
        password=password,
        email=email,
        role=role,
        real_name=payload.get("real_name", ""),
        mobile=payload.get("mobile", ""),
    )
    login(request, user)
    return JsonResponse({"user": serialize_user(user)}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    username = payload.get("username") or ""
    password = payload.get("password") or ""
    user = authenticate(request, username=username, password=password)
    if user is None:
        return json_error("invalid username or password", 401)

    login(request, user)
    return JsonResponse({"user": serialize_user(user)})


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def logout_view(request: HttpRequest) -> JsonResponse:
    logout(request)
    return JsonResponse({"message": "logged out"})


@require_GET
@login_required_json
def me(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"user": serialize_user(request.user)})


@csrf_exempt
@require_http_methods(["POST"])
def send_reset_code(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    if not username or not email:
        return json_error("username and email are required")

    user = User.objects.filter(username=username, email=email).first()
    if user is None:
        return json_error("user not found", 404)
    if not user.email:
        return json_error("user email is empty", 409)

    notification = send_password_reset_code(user=user)
    return JsonResponse(
        {
            "message": "verification code sent",
            "notification_status": notification.status,
            "ttl_seconds": settings.PASSWORD_RESET_CODE_TTL,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def reset_password(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    username = (payload.get("username") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    code = (payload.get("code") or "").strip()
    new_password = payload.get("new_password") or ""

    if not username or not email or not code or not new_password:
        return json_error("username, email, code and new_password are required")
    if len(new_password) < 6:
        return json_error("new_password must be at least 6 characters")

    user = User.objects.filter(username=username, email=email).first()
    if user is None:
        return json_error("user not found", 404)

    state = get_password_reset_state(email)
    if not state:
        return json_error("verification code expired or not found", 410)
    if int(state.get("attempts", 0)) >= settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS:
        clear_password_reset_state(email)
        return json_error("verification code retry limit exceeded", 429)
    if state.get("user_id") != user.id or state.get("code") != code:
        state = increment_password_reset_attempts(email)
        remaining_attempts = max(settings.PASSWORD_RESET_CODE_MAX_ATTEMPTS - int((state or {}).get("attempts", 0)), 0)
        return JsonResponse({"error": "invalid verification code", "remaining_attempts": remaining_attempts}, status=400)

    user.set_password(new_password)
    user.save(update_fields=["password"])
    clear_password_reset_state(email)
    return JsonResponse({"message": "password reset successful"})
