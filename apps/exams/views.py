import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.permissions import login_required_json, role_required, user_can_manage_exams
from apps.judge.services import judge_answer

from .models import Answer, Exam, ExamQuestion, KnowledgeTag, Question, Submission

User = get_user_model()


def parse_json(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValueError("request body must be valid JSON")


def json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def serialize_question(question: Question, include_answer: bool = True) -> dict:
    data = {
        "id": question.id,
        "title": question.title,
        "question_type": question.question_type,
        "difficulty": question.difficulty,
        "language": question.language,
        "prompt": question.prompt,
        "options": question.options,
        "reference_answer": question.reference_answer,
        "tags": list(question.tags.values_list("name", flat=True)),
    }
    if include_answer:
        data["correct_answer"] = question.correct_answer
    return data


def serialize_exam(exam: Exam) -> dict:
    return {
        "id": exam.id,
        "title": exam.title,
        "description": exam.description,
        "starts_at": exam.starts_at.isoformat(),
        "ends_at": exam.ends_at.isoformat(),
        "duration_minutes": exam.duration_minutes,
        "status": exam.status,
        "created_by": {
            "id": exam.created_by_id,
            "username": exam.created_by.username,
            "role": exam.created_by.role,
        },
        "question_count": exam.exam_questions.count(),
        "questions": [
            {
                "question_id": item.question_id,
                "order": item.order,
                "score": float(item.score),
                "question": serialize_question(item.question, include_answer=False),
            }
            for item in exam.exam_questions.select_related("question")
        ],
    }


def serialize_submission(submission: Submission) -> dict:
    return {
        "id": submission.id,
        "student": {
            "id": submission.student_id,
            "username": submission.student.username,
            "email": submission.student.email,
        },
        "status": submission.status,
        "total_score": float(submission.total_score),
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "answer_count": submission.answers.count(),
    }


def serialize_exam_analytics(exam: Exam) -> dict:
    submissions = list(
        exam.submissions.select_related("student").prefetch_related("answers__question").order_by("-total_score", "submitted_at", "id")
    )
    exam_questions = list(exam.exam_questions.select_related("question").order_by("order", "id"))
    completed_submissions = [item for item in submissions if item.status == Submission.Status.COMPLETED]
    finished_submissions = [item for item in submissions if item.status in {Submission.Status.COMPLETED, Submission.Status.JUDGING}]
    score_values = [float(item.total_score) for item in finished_submissions]

    distribution = {
        "excellent": sum(1 for score in score_values if score >= 90),
        "good": sum(1 for score in score_values if 75 <= score < 90),
        "pass": sum(1 for score in score_values if 60 <= score < 75),
        "fail": sum(1 for score in score_values if score < 60),
    }

    leaderboard = [
        {
            "submission_id": item.id,
            "student_id": item.student_id,
            "username": item.student.username,
            "status": item.status,
            "total_score": float(item.total_score),
            "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
        }
        for item in finished_submissions[:10]
    ]

    question_stats = []
    for exam_question in exam_questions:
        related_answers = []
        for submission in submissions:
            for answer in submission.answers.all():
                if answer.question_id == exam_question.question_id:
                    related_answers.append(answer)
                    break

        correct_count = sum(1 for answer in related_answers if answer.judge_status == Answer.JudgeStatus.ACCEPTED)
        avg_score = sum(float(answer.auto_score) for answer in related_answers) / len(related_answers) if related_answers else 0.0
        question_stats.append(
            {
                "question_id": exam_question.question_id,
                "title": exam_question.question.title,
                "question_type": exam_question.question.question_type,
                "score": float(exam_question.score),
                "answer_count": len(related_answers),
                "correct_count": correct_count,
                "accuracy_rate": round(correct_count / len(related_answers), 4) if related_answers else 0.0,
                "average_score": round(avg_score, 2),
            }
        )

    return {
        "exam": {
            "id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "question_count": len(exam_questions),
        },
        "summary": {
            "submission_count": len(submissions),
            "completed_count": len(completed_submissions),
            "in_progress_count": sum(1 for item in submissions if item.status == Submission.Status.IN_PROGRESS),
            "judging_count": sum(1 for item in submissions if item.status == Submission.Status.JUDGING),
            "average_score": round(sum(score_values) / len(score_values), 2) if score_values else 0.0,
            "highest_score": max(score_values) if score_values else 0.0,
            "lowest_score": min(score_values) if score_values else 0.0,
        },
        "score_distribution": distribution,
        "leaderboard": leaderboard,
        "question_stats": question_stats,
    }


def normalize_single_answer(payload: dict):
    if isinstance(payload, dict):
        return payload.get("value")
    return payload


def normalize_multiple_answer(payload: dict) -> list:
    if isinstance(payload, dict):
        values = payload.get("values", [])
    elif isinstance(payload, list):
        values = payload
    else:
        values = []
    return sorted(str(item) for item in values)


def score_objective_answer(answer: Answer, exam_question: ExamQuestion) -> Decimal:
    question = exam_question.question
    if question.question_type == Question.QuestionType.SINGLE:
        expected = str(question.correct_answer.get("value", ""))
        actual = str(normalize_single_answer(answer.answer_payload) or "")
        is_correct = actual == expected
    elif question.question_type == Question.QuestionType.MULTIPLE:
        expected = sorted(str(item) for item in question.correct_answer.get("values", []))
        actual = normalize_multiple_answer(answer.answer_payload)
        is_correct = actual == expected
    else:
        return judge_answer(answer, exam_question)

    answer.judge_status = Answer.JudgeStatus.ACCEPTED if is_correct else Answer.JudgeStatus.WRONG
    answer.judge_feedback = "答案正确" if is_correct else "答案错误"
    answer.auto_score = exam_question.score if is_correct else Decimal("0")
    answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
    return Decimal(answer.auto_score)


def parse_exam_datetime(value, field_name: str):
    parsed = parse_datetime(value or "")
    if parsed is None:
        raise ValueError(f"{field_name} must be a valid ISO datetime string")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def ensure_submission_access(user, submission: Submission) -> bool:
    return submission.student_id == user.id or user_can_manage_exams(user)


def sync_question_tags(question: Question, tag_names) -> None:
    tags = []
    for tag_name in tag_names or []:
        if not tag_name:
            continue
        tag, _ = KnowledgeTag.objects.get_or_create(name=str(tag_name))
        tags.append(tag)
    question.tags.set(tags)


def replace_exam_questions(exam: Exam, question_items) -> None:
    exam.exam_questions.all().delete()
    for index, item in enumerate(question_items or [], start=1):
        question = get_object_or_404(Question, pk=item.get("question_id"))
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            order=item.get("order", index),
            score=Decimal(str(item.get("score", 0))),
        )


@require_GET
@login_required_json
def overview(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "exam_count": Exam.objects.count(),
            "question_count": Question.objects.count(),
            "submission_count": Submission.objects.count(),
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required_json
def questions(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        include_answer = user_can_manage_exams(request.user)
        results = [serialize_question(item, include_answer=include_answer) for item in Question.objects.prefetch_related("tags").order_by("id")]
        return JsonResponse({"results": results})

    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)

    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    title = payload.get("title")
    question_type = payload.get("question_type")
    prompt = payload.get("prompt")
    if not title or not question_type or not prompt:
        return json_error("title, question_type and prompt are required")

    question = Question.objects.create(
        title=title,
        question_type=question_type,
        difficulty=payload.get("difficulty", Question.Difficulty.MEDIUM),
        language=payload.get("language", ""),
        prompt=prompt,
        options=payload.get("options", []),
        correct_answer=payload.get("correct_answer", {}),
        reference_answer=payload.get("reference_answer", ""),
    )
    sync_question_tags(question, payload.get("tags", []))

    return JsonResponse(serialize_question(question), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@login_required_json
def question_detail(request: HttpRequest, question_id: int) -> JsonResponse:
    question = get_object_or_404(Question.objects.prefetch_related("tags"), pk=question_id)
    include_answer = user_can_manage_exams(request.user)

    if request.method == "GET":
        return JsonResponse(serialize_question(question, include_answer=include_answer))

    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)

    if request.method == "DELETE":
        if question.exam_questions.exists() or question.answers.exists():
            return json_error("question is already in use and cannot be deleted", 409)
        question.delete()
        return JsonResponse({"message": "question deleted"})

    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    for field in ["title", "question_type", "difficulty", "language", "prompt", "options", "correct_answer", "reference_answer"]:
        if field in payload:
            setattr(question, field, payload[field])
    question.save()
    if "tags" in payload:
        sync_question_tags(question, payload.get("tags", []))
    question.refresh_from_db()
    return JsonResponse(serialize_question(question))


@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required_json
def exams(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        queryset = Exam.objects.select_related("created_by").prefetch_related("exam_questions__question").order_by("id")
        return JsonResponse({"results": [serialize_exam(item) for item in queryset]})

    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)

    try:
        payload = parse_json(request)
        starts_at = parse_exam_datetime(payload.get("starts_at"), "starts_at")
        ends_at = parse_exam_datetime(payload.get("ends_at"), "ends_at")
    except ValueError as exc:
        return json_error(str(exc))

    title = payload.get("title")
    if not title:
        return json_error("title is required")

    question_items = payload.get("questions", [])

    with transaction.atomic():
        exam = Exam.objects.create(
            title=title,
            description=payload.get("description", ""),
            starts_at=starts_at,
            ends_at=ends_at,
            duration_minutes=payload.get("duration_minutes", 120),
            status=payload.get("status", Exam.Status.DRAFT),
            created_by=request.user,
        )
        replace_exam_questions(exam, question_items)

    exam = Exam.objects.select_related("created_by").prefetch_related("exam_questions__question").get(pk=exam.pk)
    return JsonResponse(serialize_exam(exam), status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@login_required_json
def exam_detail(request: HttpRequest, exam_id: int) -> JsonResponse:
    exam = get_object_or_404(Exam.objects.select_related("created_by").prefetch_related("exam_questions__question"), pk=exam_id)

    if request.method == "GET":
        return JsonResponse(serialize_exam(exam))

    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)

    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    with transaction.atomic():
        if "title" in payload:
            exam.title = payload["title"]
        if "description" in payload:
            exam.description = payload["description"]
        if "starts_at" in payload:
            exam.starts_at = parse_exam_datetime(payload.get("starts_at"), "starts_at")
        if "ends_at" in payload:
            exam.ends_at = parse_exam_datetime(payload.get("ends_at"), "ends_at")
        if "duration_minutes" in payload:
            exam.duration_minutes = payload["duration_minutes"]
        if "status" in payload:
            exam.status = payload["status"]
        exam.save()
        if "questions" in payload:
            replace_exam_questions(exam, payload.get("questions", []))

    exam.refresh_from_db()
    return JsonResponse(serialize_exam(exam))


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def publish_exam(request: HttpRequest, exam_id: int) -> JsonResponse:
    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)
    exam = get_object_or_404(Exam, pk=exam_id)
    exam.status = Exam.Status.PUBLISHED
    exam.save(update_fields=["status", "updated_at"])
    return JsonResponse({"message": "exam published", "status": exam.status})


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def finish_exam(request: HttpRequest, exam_id: int) -> JsonResponse:
    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)
    exam = get_object_or_404(Exam, pk=exam_id)
    exam.status = Exam.Status.FINISHED
    exam.ends_at = timezone.now()
    exam.save(update_fields=["status", "ends_at", "updated_at"])
    return JsonResponse({"message": "exam finished", "status": exam.status})


@require_GET
@login_required_json
def exam_submissions(request: HttpRequest, exam_id: int) -> JsonResponse:
    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)
    exam = get_object_or_404(Exam, pk=exam_id)
    submissions = exam.submissions.select_related("student").prefetch_related("answers").order_by("id")
    return JsonResponse({"exam_id": exam.id, "results": [serialize_submission(item) for item in submissions]})


@require_GET
@login_required_json
def exam_analytics(request: HttpRequest, exam_id: int) -> JsonResponse:
    if not user_can_manage_exams(request.user):
        return json_error("permission denied", 403)
    exam = get_object_or_404(Exam, pk=exam_id)
    return JsonResponse(serialize_exam_analytics(exam))


@csrf_exempt
@require_http_methods(["POST"])
@role_required(User.Role.STUDENT)
def start_submission(request: HttpRequest, exam_id: int) -> JsonResponse:
    exam = get_object_or_404(Exam.objects.select_related("created_by").prefetch_related("exam_questions__question"), pk=exam_id)
    if exam.status != Exam.Status.PUBLISHED:
        return json_error("exam is not published", status=409)
    now = timezone.now()
    if exam.starts_at > now or exam.ends_at < now:
        return json_error("exam is not currently active", status=409)

    submission, created = Submission.objects.get_or_create(exam=exam, student=request.user)
    if not created and submission.status != Submission.Status.IN_PROGRESS:
        return json_error("submission already finished", status=409)

    return JsonResponse(
        {
            "submission_id": submission.id,
            "created": created,
            "status": submission.status,
            "exam": serialize_exam(exam),
        },
        status=201 if created else 200,
    )


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def save_answers(request: HttpRequest, submission_id: int) -> JsonResponse:
    submission = get_object_or_404(Submission.objects.select_related("exam", "student"), pk=submission_id)
    if not ensure_submission_access(request.user, submission):
        return json_error("permission denied", 403)
    if submission.status != Submission.Status.IN_PROGRESS:
        return json_error("submission is not editable", status=409)

    try:
        payload = parse_json(request)
    except ValueError as exc:
        return json_error(str(exc))

    answers_payload = payload.get("answers", [])
    if not isinstance(answers_payload, list):
        return json_error("answers must be a list")

    exam_question_ids = set(submission.exam.exam_questions.values_list("question_id", flat=True))
    saved_items = []
    for item in answers_payload:
        question_id = item.get("question_id")
        if question_id not in exam_question_ids:
            return json_error(f"question {question_id} does not belong to this exam")
        question = Question.objects.get(pk=question_id)
        answer, _ = Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={
                "answer_payload": item.get("answer_payload", {}),
                "source_code": item.get("source_code", ""),
            },
        )
        saved_items.append(
            {
                "question_id": question_id,
                "answer_id": answer.id,
                "judge_status": answer.judge_status,
            }
        )

    return JsonResponse({"submission_id": submission.id, "saved": saved_items})


@csrf_exempt
@require_http_methods(["POST"])
@login_required_json
def finish_submission(request: HttpRequest, submission_id: int) -> JsonResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("exam", "student").prefetch_related("answers__question", "exam__exam_questions__question"),
        pk=submission_id,
    )
    if not ensure_submission_access(request.user, submission):
        return json_error("permission denied", 403)
    if submission.status != Submission.Status.IN_PROGRESS:
        return json_error("submission already finished", status=409)

    answer_map = {item.question_id: item for item in submission.answers.all()}
    total_score = Decimal("0")
    pending_programming = 0

    for exam_question in submission.exam.exam_questions.all():
        answer = answer_map.get(exam_question.question_id)
        if answer is None:
            continue
        total_score += score_objective_answer(answer, exam_question)
        answer.refresh_from_db()
        if exam_question.question.question_type == Question.QuestionType.PROGRAM and answer.judge_status == Answer.JudgeStatus.PENDING:
            pending_programming += 1

    submission.total_score = total_score
    submission.submitted_at = timezone.now()
    submission.status = Submission.Status.JUDGING if pending_programming else Submission.Status.COMPLETED
    submission.save(update_fields=["total_score", "submitted_at", "status", "updated_at"])

    return JsonResponse(
        {
            "submission_id": submission.id,
            "status": submission.status,
            "total_score": float(submission.total_score),
            "pending_programming": pending_programming,
        }
    )


@require_GET
@login_required_json
def submission_detail(request: HttpRequest, submission_id: int) -> JsonResponse:
    submission = get_object_or_404(
        Submission.objects.select_related("student", "exam").prefetch_related("answers__question__answers", "answers__question"),
        pk=submission_id,
    )
    if not ensure_submission_access(request.user, submission):
        return json_error("permission denied", 403)

    return JsonResponse(
        {
            "id": submission.id,
            "exam_id": submission.exam_id,
            "student_id": submission.student_id,
            "status": submission.status,
            "total_score": float(submission.total_score),
            "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
            "answers": [
                {
                    "question_id": item.question_id,
                    "judge_status": item.judge_status,
                    "auto_score": float(item.auto_score),
                    "judge_feedback": item.judge_feedback,
                    "judge_result": item.judge_task.result_payload if hasattr(item, "judge_task") else {},
                }
                for item in submission.answers.select_related("question").all().order_by("question_id")
            ],
        }
    )
