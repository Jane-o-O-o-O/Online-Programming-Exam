from django.urls import path

from .views import exams, finish_submission, overview, questions, save_answers, start_submission, submission_detail

urlpatterns = [
    path("overview/", overview, name="exam-overview"),
    path("questions/", questions, name="question-list-create"),
    path("exams/", exams, name="exam-list-create"),
    path("exams/<int:exam_id>/start/", start_submission, name="exam-start"),
    path("submissions/<int:submission_id>/answers/", save_answers, name="submission-save-answers"),
    path("submissions/<int:submission_id>/finish/", finish_submission, name="submission-finish"),
    path("submissions/<int:submission_id>/", submission_detail, name="submission-detail"),
]
