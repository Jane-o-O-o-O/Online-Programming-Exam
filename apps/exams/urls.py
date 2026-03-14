from django.urls import path

from .views import (
    exam_analytics,
    exam_detail,
    exam_submissions,
    exams,
    finish_exam,
    finish_submission,
    overview,
    publish_exam,
    question_detail,
    questions,
    save_answers,
    start_submission,
    submission_detail,
)

urlpatterns = [
    path("overview/", overview, name="exam-overview"),
    path("questions/", questions, name="question-list-create"),
    path("questions/<int:question_id>/", question_detail, name="question-detail"),
    path("exams/", exams, name="exam-list-create"),
    path("exams/<int:exam_id>/", exam_detail, name="exam-detail"),
    path("exams/<int:exam_id>/publish/", publish_exam, name="exam-publish"),
    path("exams/<int:exam_id>/finish/", finish_exam, name="exam-finish"),
    path("exams/<int:exam_id>/submissions/", exam_submissions, name="exam-submissions"),
    path("exams/<int:exam_id>/analytics/", exam_analytics, name="exam-analytics"),
    path("exams/<int:exam_id>/start/", start_submission, name="exam-start"),
    path("submissions/<int:submission_id>/answers/", save_answers, name="submission-save-answers"),
    path("submissions/<int:submission_id>/finish/", finish_submission, name="submission-finish"),
    path("submissions/<int:submission_id>/", submission_detail, name="submission-detail"),
]
