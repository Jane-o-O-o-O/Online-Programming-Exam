import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import Submission


class LLMServiceError(Exception):
    pass


def clip_text(value, limit: int = 4000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...<truncated>"


def siliconflow_is_configured() -> bool:
    return bool(settings.SILICONFLOW_API_KEY and settings.SILICONFLOW_MODEL and settings.SILICONFLOW_BASE_URL)


def llm_runtime() -> dict:
    return {
        "provider": "siliconflow",
        "base_url": settings.SILICONFLOW_BASE_URL,
        "model": settings.SILICONFLOW_MODEL,
        "configured": siliconflow_is_configured(),
    }


def call_siliconflow_chat(messages, *, temperature: float = 0.2) -> dict:
    if not siliconflow_is_configured():
        raise LLMServiceError("siliconflow is not configured")

    payload = {
        "model": settings.SILICONFLOW_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    base_url = settings.SILICONFLOW_BASE_URL.rstrip("/")
    request = Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.SILICONFLOW_TIMEOUT) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LLMServiceError(f"siliconflow request failed: {exc.code} {clip_text(detail, 300)}") from exc
    except URLError as exc:
        raise LLMServiceError(f"siliconflow connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LLMServiceError("siliconflow request timed out") from exc

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("siliconflow returned invalid JSON") from exc

    try:
        content = parsed["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise LLMServiceError("siliconflow response is missing message content") from exc

    return {
        "provider": "siliconflow",
        "model": settings.SILICONFLOW_MODEL,
        "content": content,
        "raw": parsed,
    }


def build_exam_analytics_prompt(exam, analytics: dict) -> list[dict]:
    exam_context = {
        "exam": analytics.get("exam", {}),
        "summary": analytics.get("summary", {}),
        "score_distribution": analytics.get("score_distribution", {}),
        "leaderboard": analytics.get("leaderboard", [])[:5],
        "question_stats": analytics.get("question_stats", []),
        "exam_schedule": {
            "starts_at": exam.starts_at.isoformat(),
            "ends_at": exam.ends_at.isoformat(),
            "duration_minutes": exam.duration_minutes,
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "你是在线编程考试系统的教学分析助手。"
                "请基于考试统计结果输出中文分析，要求包含总体表现、风险点、教学建议、下一次出卷建议。"
                "结论必须贴合提供的数据，不要臆造未给出的事实。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请分析下面这场考试，并输出 4 个部分：\n"
                "1. 总体表现\n"
                "2. 风险点\n"
                "3. 教学改进建议\n"
                "4. 出卷优化建议\n\n"
                f"考试数据：\n{json.dumps(exam_context, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_submission_feedback_prompt(submission: Submission) -> list[dict]:
    answer_items = []
    for answer in submission.answers.select_related("question").all().order_by("question_id"):
        answer_items.append(
            {
                "question_id": answer.question_id,
                "title": answer.question.title,
                "question_type": answer.question.question_type,
                "prompt": clip_text(answer.question.prompt, 800),
                "reference_answer": clip_text(answer.question.reference_answer, 600),
                "judge_status": answer.judge_status,
                "auto_score": float(answer.auto_score),
                "judge_feedback": clip_text(answer.judge_feedback, 1000),
                "answer_payload": answer.answer_payload,
                "source_code": clip_text(answer.source_code, 2000),
            }
        )

    submission_context = {
        "submission_id": submission.id,
        "exam": {
            "id": submission.exam_id,
            "title": submission.exam.title,
        },
        "student": {
            "id": submission.student_id,
            "username": submission.student.username,
        },
        "status": submission.status,
        "total_score": float(submission.total_score),
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "answers": answer_items,
    }

    return [
        {
            "role": "system",
            "content": (
                "你是在线编程考试系统的学习辅导助手。"
                "请基于学生本次提交结果给出中文反馈，重点指出做得好的地方、失分原因、改进建议。"
                "如果有编程题，请优先解释判题反馈并给出可执行的修正方向，不要编造未出现的报错。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请针对下面这份考试提交生成学习反馈，输出 3 个部分：\n"
                "1. 本次表现总结\n"
                "2. 主要问题\n"
                "3. 下一步改进建议\n\n"
                f"提交数据：\n{json.dumps(submission_context, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def generate_exam_analytics_summary(exam, analytics: dict) -> dict:
    messages = build_exam_analytics_prompt(exam, analytics)
    return call_siliconflow_chat(messages, temperature=0.3)


def generate_submission_feedback(submission: Submission) -> dict:
    messages = build_submission_feedback_prompt(submission)
    return call_siliconflow_chat(messages, temperature=0.2)
