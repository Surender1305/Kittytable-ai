# timetable/timetable_generator.py

import random
from collections import defaultdict
from django.db import transaction
from django.conf import settings

from .models import Teacher, Subject, ClassGroup, ClassSubject, TimetableEntry


DAYS_PER_WEEK = getattr(settings, "DAYS_PER_WEEK", 5)
PERIODS_PER_DAY = getattr(settings, "PERIODS_PER_DAY", 7)

# Breaks are AFTER these periods (0-based):
# - after period 1 (after P2)
# - after period 3 (after P4)
# - after period 5 (after P6)
BREAK_AFTER_PERIODS = {1, 3, 5}


class SchedulingError(Exception):
    pass


def _get_teacher_data():
    """
    Returns:
      - teachers_by_subject[subject_id] -> [teacher_id, ...]
      - teacher_availability[teacher_id][day] -> set(periods)
      - max_hours_per_day[teacher_id]
    """
    teachers = Teacher.objects.prefetch_related("subjects").all()

    teachers_by_subject = defaultdict(list)
    teacher_availability = {}
    max_hours_per_day = {}

    for t in teachers:
        subj_ids = set(t.subjects.values_list("id", flat=True))
        max_hours_per_day[t.id] = t.max_hours_per_day or 4

        raw = t.availability or {}
        avail = {}
        for d in range(DAYS_PER_WEEK):
            periods = raw.get(str(d), list(range(PERIODS_PER_DAY)))
            avail[d] = set(periods)
        teacher_availability[t.id] = avail

        for sid in subj_ids:
            teachers_by_subject[sid].append(t.id)

    return teachers_by_subject, teacher_availability, max_hours_per_day


def _get_class_requirements():
    """
        Returns:
          class_requirements[class_id] = [
            {
              "subject_id": sid,
              "hours": h,
              "subject_name": "...",
              "is_lab": bool,
              "preferred_teacher_id": teacher_id or None,
            },
            ...
          ]
          class_ids = [...]
        """
    class_reqs = defaultdict(list)
    qs = ClassSubject.objects.select_related("class_group", "subject", "teacher")
    for cs in qs:
        class_reqs[cs.class_group_id].append(
            {
                "subject_id": cs.subject_id,
                "hours": cs.hours_per_week,
                "subject_name": cs.subject.name,
                "is_lab": cs.is_lab,
                "preferred_teacher_id": cs.teacher_id,  # <= important
            }
        )
    return class_reqs, sorted(class_reqs.keys())


def _init_state(class_ids, teacher_ids):
    """
    In-memory scheduling state.
    """
    class_timetable = {
        cid: [[None for _ in range(PERIODS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]
        for cid in class_ids
    }
    teacher_busy = {
        tid: [[False for _ in range(PERIODS_PER_DAY)] for _ in range(DAYS_PER_WEEK)]
        for tid in teacher_ids
    }
    teacher_hours_per_day = {
        tid: [0 for _ in range(DAYS_PER_WEEK)] for tid in teacher_ids
    }
    return class_timetable, teacher_busy, teacher_hours_per_day


def _find_candidate_slots_for_lab(
    class_id,
    subject_id,
    teachers_for_subject,
    teacher_availability,
    teacher_busy,
    teacher_hours_per_day,
    max_hours_per_day,
    class_timetable,
):
    """
    Find (day, period_start, teacher_id) options for a 2-period lab,
    ensuring the lab does not cross breaks.

    Labs are allowed only within continuous blocks:
      - (0,1), (2,3), (4,5)
    Not allowed to start at periods which have a break after them:
      - i.e., period in BREAK_AFTER_PERIODS (1,3,5)
    """
    candidates = []

    for day in range(DAYS_PER_WEEK):
        for period in range(PERIODS_PER_DAY - 1):  # need period and period+1

            # Don't start a lab at a slot after which there is a break:
            # that would split the lab around the break.
            if period in BREAK_AFTER_PERIODS:
                continue

            # Class must be free in both periods
            if (
                class_timetable[class_id][day][period] is not None
                or class_timetable[class_id][day][period + 1] is not None
            ):
                continue

            for tid in teachers_for_subject:
                # Teacher available in both periods?
                if (
                    period not in teacher_availability[tid][day]
                    or period + 1 not in teacher_availability[tid][day]
                ):
                    continue

                # Teacher not already busy in those periods?
                if teacher_busy[tid][day][period] or teacher_busy[tid][day][period + 1]:
                    continue

                # Enough daily hours left for a 2-hour block?
                if teacher_hours_per_day[tid][day] + 2 > max_hours_per_day[tid]:
                    continue

                candidates.append((day, period, tid))

    return candidates


def _find_candidate_slots_for_lecture(
    class_id,
    subject_id,
    teachers_for_subject,
    teacher_availability,
    teacher_busy,
    teacher_hours_per_day,
    max_hours_per_day,
    class_timetable,
):
    """
    Find (day, period, teacher_id) options for a 1-period lecture.
    """
    candidates = []

    for day in range(DAYS_PER_WEEK):
        for period in range(PERIODS_PER_DAY):
            if class_timetable[class_id][day][period] is not None:
                continue

            for tid in teachers_for_subject:
                if period not in teacher_availability[tid][day]:
                    continue
                if teacher_busy[tid][day][period]:
                    continue
                if teacher_hours_per_day[tid][day] + 1 > max_hours_per_day[tid]:
                    continue

                candidates.append((day, period, tid))

    return candidates


def generate_full_timetable():
    """
    Generate timetable for all classes.

    - 5 days/week, 7 periods/day.
    - Labs (is_lab=True) scheduled as 2 consecutive periods that do not cross breaks.
    - Lectures scheduled as 1 period.
    - Clears existing TimetableEntry and recreates them.
    """
    teachers_by_subject, teacher_availability, max_hours_per_day = _get_teacher_data()
    class_requirements, class_ids = _get_class_requirements()

    if not class_ids:
        raise SchedulingError("No class/subject requirements defined.")

    teacher_ids = list(max_hours_per_day.keys())
    if not teacher_ids:
        raise SchedulingError("No teachers defined.")

    class_timetable, teacher_busy, teacher_hours_per_day = _init_state(class_ids, teacher_ids)

    random.seed(42)

    for cid in class_ids:
        reqs = class_requirements[cid]

        lab_blocks = []  # items: (subject_id, preferred_teacher_id)
        lecture_sessions = []  # items: (subject_id, preferred_teacher_id)

        for r in reqs:
            sid = r["subject_id"]
            hours = r["hours"]
            is_lab = r["is_lab"]
            preferred_tid = r["preferred_teacher_id"]

            if is_lab:
                if hours % 2 != 0:
                    ...
                blocks = hours // 2
                lab_blocks.extend([(sid, preferred_tid)] * blocks)
            else:
                lecture_sessions.extend([(sid, preferred_tid)] * hours)

        random.shuffle(lab_blocks)
        random.shuffle(lecture_sessions)

        # ---- 1) Schedule labs ----
        for subject_id, preferred_tid in lab_blocks:
            teachers_for_subject = teachers_by_subject.get(subject_id, [])
            if preferred_tid:
                if preferred_tid not in teachers_for_subject:
                    subject_name = Subject.objects.get(id=subject_id).name
                    class_name = ClassGroup.objects.get(id=cid).name
                    raise SchedulingError(
                        f"Assigned teacher for lab '{subject_name}' in class '{class_name}' "
                        "does not have this subject in their profile."
                    )
                teachers_for_subject = [preferred_tid]  # force this teacher

            ...
            # then use teachers_for_subject in _find_candidate_slots_for_lab()

        # ---- 2) Schedule lectures ----
        for subject_id, preferred_tid in lecture_sessions:
            teachers_for_subject = teachers_by_subject.get(subject_id, [])
            if preferred_tid:
                if preferred_tid not in teachers_for_subject:
                    subject_name = Subject.objects.get(id=subject_id).name
                    class_name = ClassGroup.objects.get(id=cid).name
                    raise SchedulingError(
                        f"Assigned teacher for subject '{subject_name}' in class '{class_name}' "
                        "does not have this subject in their profile."
                    )
                teachers_for_subject = [preferred_tid]  # force this teacher


            # then use teachers_for_subject in _find_candidate_slots_for_lecture()

            if not teachers_for_subject:
                subject_name = Subject.objects.get(id=subject_id).name
                class_name = ClassGroup.objects.get(id=cid).name
                raise SchedulingError(
                    f"No teacher available to teach subject '{subject_name}' for class '{class_name}'."
                )

            candidates = _find_candidate_slots_for_lecture(
                class_id=cid,
                subject_id=subject_id,
                teachers_for_subject=teachers_for_subject,
                teacher_availability=teacher_availability,
                teacher_busy=teacher_busy,
                teacher_hours_per_day=teacher_hours_per_day,
                max_hours_per_day=max_hours_per_day,
                class_timetable=class_timetable,
            )

            if not candidates:
                cls_name = ClassGroup.objects.get(id=cid).name
                subject_name = Subject.objects.get(id=subject_id).name
                raise SchedulingError(
                    f"Cannot schedule all lecture sessions for class '{cls_name}', subject '{subject_name}'. "
                    "Constraints too tight or insufficient teacher availability."
                )

            def lect_load_metric(c):
                d, p, tid = c
                return teacher_hours_per_day[tid][d]

            day, period, tid = min(candidates, key=lect_load_metric)

            class_timetable[cid][day][period] = {
                "subject_id": subject_id,
                "teacher_id": tid,
            }
            teacher_busy[tid][day][period] = True
            teacher_hours_per_day[tid][day] += 1

    # ---- Persist to DB ----
    with transaction.atomic():
        TimetableEntry.objects.all().delete()

        entries = []
        for cid in class_ids:
            for day in range(DAYS_PER_WEEK):
                for period in range(PERIODS_PER_DAY):
                    cell = class_timetable[cid][day][period]
                    if cell is None:
                        continue
                    entries.append(
                        TimetableEntry(
                            class_group_id=cid,
                            subject_id=cell["subject_id"],
                            teacher_id=cell["teacher_id"],
                            day_of_week=day,
                            period=period,
                        )
                    )

        TimetableEntry.objects.bulk_create(entries)

    return True