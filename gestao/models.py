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


class EmployeeWorkAssignment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    work_block = models.ForeignKey('WorkBlock', on_delete=models.CASCADE)
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Duration in hours for this employee")
    is_completed = models.BooleanField(default=False)
    assigned_date = models.DateTimeField(auto_now_add=True)
    completed_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['employee', 'work_block']

    def __str__(self):
        return f"{self.employee.name} - {self.work_block} - {self.duration}h"




class WorkBlock(models.Model):
    name = models.CharField(max_length=200, blank=True, default="")
    localization = models.CharField(max_length=200, blank=True, default="")
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    day_of_month = models.IntegerField()
    month = models.IntegerField(default=timezone.now().month)
    year = models.IntegerField(default=timezone.now().year)
    employees_assigned = models.ManyToManyField(Employee, through=EmployeeWorkAssignment, related_name='assigned_blocks', blank=True)
    archived = models.BooleanField(default=False)
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Default duration in hours")
    hourly_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Value per hour for this work block")
    constant = models.BooleanField(default=False, help_text="If true, repeats on same weekday for the month")

    def clean(self):
        if self.day_of_month < 1 or self.day_of_month > 31:
            raise ValidationError("Day of month must be between 1 and 31.")
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")

    def get_employees_concluded(self):
        """Get employees who have completed this work block"""
        return Employee.objects.filter(
            employeeworkassignment__work_block=self,
            employeeworkassignment__is_completed=True
        )

    def get_employee_duration(self, employee):
        """Get duration for specific employee or default duration"""
        try:
            assignment = EmployeeWorkAssignment.objects.get(work_block=self, employee=employee)
            return assignment.duration
        except EmployeeWorkAssignment.DoesNotExist:
            return self.duration

    def is_employee_completed(self, employee):
        """Check if employee has completed this work block"""
        try:
            assignment = EmployeeWorkAssignment.objects.get(work_block=self, employee=employee)
            return assignment.is_completed
        except EmployeeWorkAssignment.DoesNotExist:
            return False





    def __str__(self):
        return f"{self.name or 'WorkBlock'} {self.day_of_month}/{self.month}/{self.year} {self.start_time}-{self.end_time}"
