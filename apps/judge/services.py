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


SYNC_LOCAL_MODE = "local"
SYNC_DOCKER_MODE = "docker"
ASYNC_LOCAL_MODE = "celery"
ASYNC_DOCKER_MODE = "celery_docker"


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


def current_judge_runtime() -> str:
    if settings.JUDGE_EXECUTION_MODE in {SYNC_DOCKER_MODE, ASYNC_DOCKER_MODE}:
        return "docker"
    return "local"


def current_judge_is_async() -> bool:
    return settings.JUDGE_EXECUTION_MODE in {ASYNC_LOCAL_MODE, ASYNC_DOCKER_MODE}


def build_solution_workspace(source_code: str) -> tuple[Path, Path]:
    judge_temp_dir = Path(settings.JUDGE_TEMP_DIR)
    judge_temp_dir.mkdir(parents=True, exist_ok=True)
    work_dir = judge_temp_dir / f"job-{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=True)
    script_path = work_dir / "solution.py"
    script_path.write_text(source_code, encoding="utf-8")
    return work_dir, script_path


def run_python_case_local(script_path: Path, work_dir: Path, case_input: str, timeout_seconds: int) -> tuple[str, str, int]:
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


def run_python_case_docker(script_path: Path, work_dir: Path, case_input: str, timeout_seconds: int) -> tuple[str, str, int]:
    volume = f"{work_dir.resolve()}:/workspace:ro"
    completed = subprocess.run(
        [
            settings.JUDGE_DOCKER_COMMAND,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            settings.JUDGE_DOCKER_MEMORY_LIMIT,
            "--cpus",
            str(settings.JUDGE_DOCKER_CPU_LIMIT),
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-v",
            volume,
            "-w",
            "/workspace",
            settings.JUDGE_DOCKER_IMAGE,
            "python",
            "-B",
            str(Path("/workspace") / script_path.name),
        ],
        input=case_input,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + settings.JUDGE_DOCKER_EXTRA_TIMEOUT_SECONDS,
        encoding="utf-8",
        errors="replace",
    )
    stdout = completed.stdout[: settings.JUDGE_MAX_OUTPUT_CHARS]
    stderr = completed.stderr[: settings.JUDGE_MAX_OUTPUT_CHARS]
    return stdout, stderr, completed.returncode


def run_python_case(source_code: str, case_input: str, timeout_seconds: int, runtime: str) -> tuple[str, str, int]:
    work_dir, script_path = build_solution_workspace(source_code)
    try:
        if runtime == "docker":
            return run_python_case_docker(script_path, work_dir, case_input, timeout_seconds)
        return run_python_case_local(script_path, work_dir, case_input, timeout_seconds)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def get_or_create_judge_task(answer: Answer) -> JudgeTask:
    docker_image = settings.JUDGE_DOCKER_IMAGE if current_judge_runtime() == "docker" else ""
    task, _ = JudgeTask.objects.get_or_create(
        answer=answer,
        defaults={
            "language": answer.question.language or "python",
            "docker_image": docker_image,
            "status": JudgeTask.Status.QUEUED,
        },
    )
    if task.docker_image != docker_image:
        task.docker_image = docker_image
        task.save(update_fields=["docker_image"])
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
    task.result_payload = {"message": "queued for async judge", "runtime": current_judge_runtime()}
    task.started_at = None
    task.finished_at = None
    task.docker_image = settings.JUDGE_DOCKER_IMAGE if current_judge_runtime() == "docker" else ""
    task.save(update_fields=["status", "result_payload", "started_at", "finished_at", "docker_image"])

    answer.judge_status = Answer.JudgeStatus.PENDING
    answer.judge_feedback = "编程题已进入异步判题队列"
    answer.auto_score = Decimal("0")
    answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])

    try:
        judge_answer_task.delay(answer.id)
        return True
    except Exception as exc:
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": f"enqueue failed: {exc}", "runtime": current_judge_runtime()}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = f"异步判题入队失败: {exc}"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        return False


def judge_program_answer(answer: Answer, exam_question: ExamQuestion) -> Decimal:
    runtime = current_judge_runtime()
    task = get_or_create_judge_task(answer)
    task.status = JudgeTask.Status.RUNNING
    task.started_at = timezone.now()
    task.finished_at = None
    task.result_payload = {"runtime": runtime}
    task.docker_image = settings.JUDGE_DOCKER_IMAGE if runtime == "docker" else ""
    task.save(update_fields=["status", "started_at", "finished_at", "result_payload", "docker_image"])

    question = answer.question
    cases = question.correct_answer.get("cases", []) if isinstance(question.correct_answer, dict) else []
    timeout_seconds = int(question.correct_answer.get("time_limit_seconds", settings.JUDGE_TIMEOUT_SECONDS)) if isinstance(question.correct_answer, dict) else settings.JUDGE_TIMEOUT_SECONDS

    if (question.language or "python").lower() != "python":
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = f"当前 {runtime} 判题模式只支持 Python 编程题"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback, "runtime": runtime}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    if not answer.source_code.strip():
        answer.judge_status = Answer.JudgeStatus.COMPILE_ERROR
        answer.judge_feedback = "未提交代码"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback, "runtime": runtime}
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "result_payload", "finished_at"])
        return Decimal("0")

    if not cases:
        answer.judge_status = Answer.JudgeStatus.RUNTIME_ERROR
        answer.judge_feedback = "编程题未配置测试用例"
        answer.auto_score = Decimal("0")
        answer.save(update_fields=["judge_status", "judge_feedback", "auto_score", "updated_at"])
        task.status = JudgeTask.Status.FAILED
        task.result_payload = {"message": answer.judge_feedback, "runtime": runtime}
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
        task.result_payload = {"message": answer.judge_feedback, "runtime": runtime}
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
            stdout, stderr, return_code = run_python_case(answer.source_code, case_input, timeout_seconds, runtime)
        except subprocess.TimeoutExpired:
            final_status = Answer.JudgeStatus.TIME_LIMIT
            final_feedback = f"第 {index} 个测试用例执行超时"
            case_results.append(build_case_result(index, "time_limit", expected=expected_output, message=final_feedback))
            break
        except FileNotFoundError as exc:
            final_status = Answer.JudgeStatus.RUNTIME_ERROR
            final_feedback = f"{runtime} 判题环境不可用: {exc}"
            case_results.append(build_case_result(index, "runtime_error", expected=expected_output, message=final_feedback))
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
    task.result_payload = {"cases": case_results, "final_status": final_status, "runtime": runtime}
    task.finished_at = timezone.now()
    task.save(update_fields=["status", "result_payload", "finished_at"])
    return Decimal(answer.auto_score)


def judge_answer(answer: Answer, exam_question: ExamQuestion) -> Decimal:
    if answer.question.question_type != answer.question.QuestionType.PROGRAM:
        return Decimal("0")

    if not current_judge_is_async():
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

    if current_judge_is_async():
        enqueue_async_judge(answer, task)
        update_submission_after_judge(answer.submission)
    else:
        judge_program_answer(answer, exam_question)
        update_submission_after_judge(answer.submission)

    task.refresh_from_db()
    return task
