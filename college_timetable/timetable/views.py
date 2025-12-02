# timetable/views.py

from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.forms import inlineformset_factory

from .models import (
    Subject,
    Teacher,
    ClassGroup,
    ClassSubject,
    TimetableEntry,
)
from .timetable_generator import generate_full_timetable, SchedulingError


# ----------------------------------------------------------------------
# Global constants
# ----------------------------------------------------------------------

DAYS_PER_WEEK = getattr(settings, "DAYS_PER_WEEK", 5)
PERIODS_PER_DAY = getattr(settings, "PERIODS_PER_DAY", 7)
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][:DAYS_PER_WEEK]


# ----------------------------------------------------------------------
# DASHBOARD / CLASS‑WISE OVERVIEW (GET /timetable/)
# ----------------------------------------------------------------------

@require_GET
def timetable_overview(request):
    """
    Dashboard (class‑centric view):
    - Shows timetable grid for each class (5 × 7)
    - Provides summary and subject‑staff details
    """
    class_groups = ClassGroup.objects.all().order_by("name")

    # Map (class_group_id, subject_id) -> is_lab (to mark lab slots in UI)
    cs_map = {
        (cs.class_group_id, cs.subject_id): cs.is_lab
        for cs in ClassSubject.objects.all()
    }

    # Preload all timetable entries and group by class_group_id
    entries_by_class = defaultdict(list)
    for e in TimetableEntry.objects.select_related("subject", "teacher", "class_group"):
        entries_by_class[e.class_group_id].append(e)

    class_tables = []

    for cg in class_groups:
        # grid[day][period] -> None or {subject, teacher, is_lab}
        grid = [[None for _ in range(PERIODS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]

        for e in entries_by_class.get(cg.id, []):
            if 0 <= e.day_of_week < DAYS_PER_WEEK and 0 <= e.period < PERIODS_PER_DAY:
                is_lab = cs_map.get((e.class_group_id, e.subject_id), False)
                grid[e.day_of_week][e.period] = {
                    "subject": e.subject,
                    "teacher": e.teacher,
                    "is_lab": is_lab,
                }

        rows = []
        for day_idx in range(DAYS_PER_WEEK):
            rows.append(
                {
                    "day_name": DAY_NAMES[day_idx],
                    "cells": grid[day_idx],
                }
            )

        class_tables.append(
            {
                "class_group": cg,
                "rows": rows,
            }
        )

    # Summary metrics
    summary = {
        "classes": class_groups.count(),
        "teachers": Teacher.objects.count(),
        "labs": ClassSubject.objects.filter(is_lab=True).count(),
        "conflicts": 0,  # you can compute real conflicts if you track them
    }

    # Subject -> staff mapping for "Subject & Staff Details" table
    subject_staff = []
    for subject in Subject.objects.all().order_by("code"):
        teacher_names = list(
            subject.teachers.order_by("name").values_list("name", flat=True)
        )
        subject_staff.append(
            {
                "subject": subject,
                "teachers": teacher_names,
            }
        )

    context = {
        "class_tables": class_tables,
        "summary": summary,
        "subject_staff": subject_staff,
    }
    return render(request, "timetable/overview.html", context)


# ----------------------------------------------------------------------
# GENERATE TIMETABLE (POST /timetable/generate/)
# ----------------------------------------------------------------------

@require_POST
def generate_timetable_view(request):
    """
    Called by the 'Generate Timetable' button on the dashboard.
    Uses timetable_generator to rebuild TimetableEntry.
    """
    try:
        generate_full_timetable()
        messages.success(request, "Timetable generated successfully.")
    except SchedulingError as e:
        messages.error(request, f"Timetable generation failed: {e}")
    except Exception as e:
        messages.error(request, f"Unexpected error during generation: {e}")
    return redirect("timetable_overview")


# ----------------------------------------------------------------------
# TEACHER‑WISE OVERVIEW (GET /timetable/teachers/)
# ----------------------------------------------------------------------

@require_GET
def teachers_overview(request):
    """
    Teacher‑centric page:
    - For each teacher: list subjects handled
    - Show a 5×7 timetable grid (days × periods)
    """
    teachers = Teacher.objects.prefetch_related("subjects").order_by("name")

    cs_map = {
        (cs.class_group_id, cs.subject_id): cs.is_lab
        for cs in ClassSubject.objects.all()
    }

    entries_by_teacher = defaultdict(list)
    for e in TimetableEntry.objects.select_related("subject", "class_group", "teacher"):
        entries_by_teacher[e.teacher_id].append(e)

    teacher_tables = []

    for teacher in teachers:
        grid = [[None for _ in range(PERIODS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]
        for e in entries_by_teacher.get(teacher.id, []):
            if 0 <= e.day_of_week < DAYS_PER_WEEK and 0 <= e.period < PERIODS_PER_DAY:
                is_lab = cs_map.get((e.class_group_id, e.subject_id), False)
                grid[e.day_of_week][e.period] = {
                    "subject": e.subject,
                    "class_group": e.class_group,
                    "is_lab": is_lab,
                }

        rows = []
        for day_idx in range(DAYS_PER_WEEK):
            rows.append({
                "day_name": DAY_NAMES[day_idx],
                "cells": grid[day_idx],
            })

        teacher_tables.append({
            "teacher": teacher,
            "subjects": list(teacher.subjects.all()),
            "rows": rows,
        })

    return render(request, "timetable/teachers.html", {"teacher_tables": teacher_tables})

# ----------------------------------------------------------------------
# CLASSES MODULE (GET /timetable/classes/)
# ----------------------------------------------------------------------

@require_GET
@require_GET
def classes_overview(request):
    class_groups = ClassGroup.objects.all().order_by("name")
    class_configs = []

    for cg in class_groups:
        subjects_info = []
        class_subjects = (
            ClassSubject.objects
            .select_related("subject", "teacher")
            .filter(class_group=cg)
            .order_by("subject__code")
        )

        for cs in class_subjects:
            subj = cs.subject
            assigned_teacher = cs.teacher.name if cs.teacher else None
            all_teachers = list(
                subj.teachers.order_by("name").values_list("name", flat=True)
            )

            subjects_info.append({
                "subject": subj,
                "hours_per_week": cs.hours_per_week,
                "is_lab": cs.is_lab,
                "assigned_teacher": assigned_teacher,
                "all_teachers": all_teachers,
            })

        class_configs.append({
            "class_group": cg,
            "subjects": subjects_info,
        })

    return render(request, "timetable/classes.html", {"class_configs": class_configs})
