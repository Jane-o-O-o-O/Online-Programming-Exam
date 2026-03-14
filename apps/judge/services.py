from __future__ import annotations

import shutil
import subprocess
import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.exams.models import Answer, ExamQuestion, Submission

from .models import JudgeTask


def normalize_output(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").strip().split("\n")).strip()


def build_case_result(index: int, status: str, *, expected: str = "", actual: str = "", message: str = "") -> dict:
    payload = {"case": index, "status": status}
    if expected:
        payload["expected"] = expected
    if actual:
        payload["actual"] = actual
    if message:
        payload["message"] = message
    return payload


def run_python_case(source_code: str, case_input: str, timeout_seconds: int) -> tuple[str, str, int]:
    judge_temp_dir = Path(settings.JUDGE_TEMP_DIR)
    judge_temp_dir.mkdir(parents=True, exist_ok=True)
    work_dir = judge_temp_dir / f"job-{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    script_path = work_dir / "solution.py"
    try:
        script_path.write_text(source_code, encoding="utf-8")
        completed = subprocess.run(
            [settings.JUDGE_PYTHON_COMMAND, str(script_path)],
            input=case_input,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
            cwd=work_dir,
        )
        stdout = completed.stdout[: settings.JUDGE_MAX_OUTPUT_CHARS]
        stderr = completed.stderr[: settings.JUDGE_MAX_OUTPUT_CHARS]
        return stdout, stderr, completed.returncode
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def get_or_create_judge_task(answer: Answer) -> JudgeTask:
    task, _ = JudgeTask.objects.get_or_create(
        answer=answer,
        defaults={
            "language": answer.question.language or "python",
            "docker_image": "",
            "status": JudgeTask.Status.QUEUED,
        },
    )
    return task


def update_submission_after_judge(submission: Submission) -> Submission:
    answers = list(submission.answers.select_related("question").all())
    total_score = sum((Decimal(item.auto_score) for item in answers), Decimal("0"))
    pending_programming = sum(
        1 for item in answers if item.question.question_type == item.question.QuestionType.PROGRAM and item.judge_status == Answer.JudgeStatus.PENDING
    )

    submission.total_score = total_score
    if submission.submitted_at:
        submission.status = Submission.Status.JUDGING if pending_programming else Submission.Status.COMPLETED
    submission.save(update_fields=["total_score", "status", "updated_at"])
    return submission


def enqueue_async_judge(answer: Answer, task: JudgeTask | None = None) -> bool:
    from .tasks import judge_answer_task

    task = task or get_or_create_judge_task(answer)
    task.status = JudgeTask.Status.QUEUED
    task.result_payload = {"message": "queued for async judge"}
    task.started_at = None
    task.finished_at = None
    task.save(update_fields=["status", "result_payload", "started_at", "finished_at"])

    answer.judge_status = Answer.JudgeStatus.PENDING
    answer.judge_feedback = "编程题已进入异步判题队列"
    answer.auto_score = Decimal("0")
    answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])

    try:
        judge_answer_task.delay(answer.id)
        return True
    except Exception as exc:
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": f"enqueue failed: {exc}"}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = f"异步判题入队失败: {exc}"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        return False


def judge_program_answer(answer: Answer, exam_question: ExamQuestion) -> Decimal:
    task = get_or_create_judge_task(answer)
    task.status = JudgeTask.Status.RUNNING
    task.started_at = timezone.now()
    task.finished_at = None
    task.result_payload = {}
    task.save(update_fields=["status", "started_at", "finished_at", "result_payload"])

    question = answer.question
    cases = question.correct_answer.get("cases", []) if isinstance(question.correct_answer, dict) else []
    timeout_seconds = int(question.correct_answer.get("time_limit_seconds", settings.JUDGE_TIMEOUT_SECONDS)) if isinstance(question.correct_answer, dict) else settings.JUDGE_TIMEOUT_SECONDS

    if (question.language or "python").lower() != "python":
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = "当前本地开发模式只支持 Python 编程题判题"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    if not answer.source_code.strip():
        answer.judge_status = Answer.JudgeStatus.COMPILE_ERROR
        answer.judge_feedback = "未提交代码"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    if not cases:
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = "编程题未配置测试用例"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    try:
        compile(answer.source_code, "solution.py", "exec")
    except SyntaxError as exc:
        answer.judge_status = Answer.JudgeStatus.COMPILE_ERROR
        answer.judge_feedback = f"语法错误: 第 {exc.lineno} 行 {exc.msg}"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    case_results = []
    final_status = Answer.JudgeStatus.ACCEPTED
    final_feedback = "全部测试用例通过"

    for index, case in enumerate(cases, start=1):
        case_input = str(case.get("input", ""))
        expected_output = str(case.get("output", ""))
        try:
            stdout, stderr, return_code = run_python_case(answer.source_code, case_input, timeout_seconds)
        except subprocess.TimeoutExpired:
            final_status = Answer.JudgeStatus.TIME_LIMIT
            final_feedback = f"第 {index} 个测试用例执行超时"
            case_results.append(build_case_result(index, "time_limit", expected=expected_output, message=final_feedback))
            break

        if return_code != 0:
            final_status = Answer.JudgeStatus.RUNTIME_ERROR
            final_feedback = stderr or f"第 {index} 个测试用例执行失败"
            case_results.append(build_case_result(index, "runtime_error", expected=expected_output, actual=stdout, message=final_feedback))
            break

        normalized_actual = normalize_output(stdout)
        normalized_expected = normalize_output(expected_output)
        if normalized_actual != normalized_expected:
            final_status = Answer.JudgeStatus.WRONG
            final_feedback = f"第 {index} 个测试用例输出不匹配"
            case_results.append(build_case_result(index, "wrong_answer", expected=normalized_expected, actual=normalized_actual, message=final_feedback))
            break

        case_results.append(build_case_result(index, "accepted", expected=normalized_expected, actual=normalized_actual))

    answer.judge_status = final_status
    answer.judge_feedback = final_feedback
    answer.auto_score = exam_question.score if final_status == Answer.JudgeStatus.ACCEPTED else Decimal("0")
    answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])

    task.status = JudgeTask.Status.SUCCESS if final_status == Answer.JudgeStatus.ACCEPTED else JudgeTask.Status.FAILED
    task.result_payload = {"cases": case_results, "final_status": final_status}
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "result_payload", "finished_at"])
    return Decimal(answer.auto_score)


def judge_answer(answer: Answer, exam_question: ExamQuestion) -> Decimal:
    if answer.question.question_type != answer.question.QuestionType.PROGRAM:
        return Decimal("0")

    if settings.JUDGE_EXECUTION_MODE == "local":
        return judge_program_answer(answer, exam_question)

    task = get_or_create_judge_task(answer)
    queued = enqueue_async_judge(answer, task)
    answer.refresh_from_db()
    return Decimal(answer.auto_score) if queued and answer.judge_status != Answer.JudgeStatus.PENDING else Decimal("0")


@transaction.atomic
def retry_judge_task(task: JudgeTask) -> JudgeTask:
    answer = task.answer
    exam_question = ExamQuestion.objects.select_related("question").get(exam=answer.submission.exam, question=answer.question)
    answer.judge_status = Answer.JudgeStatus.PENDING
    answer.judge_feedback = "重新进入判题流程"
    answer.auto_score = Decimal("0")
    answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])

    if settings.JUDGE_EXECUTION_MODE == "local":
        judge_program_answer(answer, exam_question)
        update_submission_after_judge(answer.submission)
    else:
        enqueue_async_judge(answer, task)
        update_submission_after_judge(answer.submission)

    task.refresh_from_db()
    return task
