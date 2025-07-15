from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User


class Client(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Employee(models.Model):
    name = models.CharField(max_length=100)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class WorkBlock(models.Model):
    name = models.CharField(max_length=200, blank=True, default="")
    localization = models.CharField(max_length=200, blank=True, default="")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    day_of_month = models.IntegerField()
    month = models.IntegerField(default=timezone.now().month)
    year = models.IntegerField(default=timezone.now().year)
    employees_assigned = models.ManyToManyField(Employee, related_name='assigned_blocks', blank=True)
    employees_concluded = models.ManyToManyField(Employee, related_name='concluded_blocks', blank=True)
    archived = models.BooleanField(default=False)
    duration = models.FloatField(help_text="Duration in hours")
    constant = models.BooleanField(default=False, help_text="If true, repeats on same weekday for the month")

    def clean(self):
        if self.day_of_month < 1 or self.day_of_month > 31:
            raise ValidationError("Day of month must be between 1 and 31.")
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self):
        return f"{self.name or 'WorkBlock'} {self.day_of_month}/{self.month}/{self.year} {self.start_time}-{self.end_time}"
