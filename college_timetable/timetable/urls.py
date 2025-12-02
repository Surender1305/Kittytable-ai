from django.urls import path
from . import views

urlpatterns = [
    path("", views.timetable_overview, name="timetable_overview"),
    path("generate/", views.generate_timetable_view, name="generate_timetable"),
    path("teachers/", views.teachers_overview, name="teachers_overview"),
    path("classes/", views.classes_overview, name="classes_overview"),

]