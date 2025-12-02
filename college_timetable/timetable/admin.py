from django.contrib import admin
from .models import Subject, Teacher, ClassGroup, ClassSubject, TimetableEntry

admin.site.register(Subject)
admin.site.register(Teacher)
admin.site.register(ClassGroup)
admin.site.register(ClassSubject)
admin.site.register(TimetableEntry)