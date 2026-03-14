from celery import shared_task

from apps.exams.models import Answer, ExamQuestion

from .services import judge_program_answer


@shared_task
def ping_judge() -> str:
    return "judge worker is alive"


@shared_task
def judge_answer_task(answer_id: int) -> str:
    answer = Answer.objects.select_related("question", "submission__exam").get(pk=answer_id)
    exam_question = ExamQuestion.objects.get(exam=answer.submission.exam, question=answer.question)
    judge_program_answer(answer, exam_question)
    answer.refresh_from_db()
    return answer.judge_status
