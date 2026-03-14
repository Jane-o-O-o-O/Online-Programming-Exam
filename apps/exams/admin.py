from django.contrib import admin

from .models import Answer, Exam, ExamQuestion, KnowledgeTag, Question, Submission

admin.site.register(KnowledgeTag)
admin.site.register(Question)
admin.site.register(Exam)
admin.site.register(ExamQuestion)
admin.site.register(Submission)
admin.site.register(Answer)
