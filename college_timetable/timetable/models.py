from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

DAYS_OF_WEEK = (
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
)


class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Teacher(models.Model):
    name = models.CharField(max_length=100)
    subjects = models.ManyToManyField(Subject, related_name="teachers")
    max_hours_per_day = models.PositiveIntegerField(default=4)

    # Availability as JSON:
    # {
    #   "0": [0,1,2,3,4,5,6],  # Monday: available in P1..P7 (0-based)
    #   "1": [0,1,2,3,4,5,6],
    #   ...
    # }
    availability = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class ClassGroup(models.Model):
    """One class/section, e.g. 'CSE-3A'."""
    name = models.CharField(max_length=50, unique=True)
    year = models.IntegerField(null=True, blank=True)
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name


# timetable/models.py

class ClassSubject(models.Model):
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="class_subjects"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    hours_per_week = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_lab = models.BooleanField(default=False)

    # This is the key: the assigned teacher for THIS subject in THIS class
    teacher = models.ForeignKey(
        Teacher,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="class_subjects",
        help_text="Primary teacher for this subject in this class.",
    )

    class Meta:
        unique_together = ("class_group", "subject")  # NOT including teacher

    def __str__(self):
        return f"{self.class_group.name} - {self.subject.code} ({self.hours_per_week} hrs/wk)"

class TimetableEntry(models.Model):
    """
    One cell in the timetable grid.
    """
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="timetable_entries")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    # 0-based index for period: 0 = P1, 1 = P2, ...
    period = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(20)])

    class Meta:
        unique_together = ("class_group", "day_of_week", "period")  # only one entry per slot
        indexes = [
            models.Index(fields=["teacher", "day_of_week", "period"]),
        ]

    def __str__(self):
        return (
            f"{self.class_group.name} | {self.get_day_of_week_display()} P{self.period + 1} "
            f"-> {self.subject.code} ({self.teacher.name})"
        )