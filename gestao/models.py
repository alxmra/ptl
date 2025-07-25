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
    contract_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Hourly rate for contracted employees (overrides workblock rates)")

    def __str__(self):
        return self.name

    @property
    def has_contract(self):
        return self.contract_hourly_rate is not None


class EmployeeWorkAssignment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    work_block = models.ForeignKey('WorkBlock', on_delete=models.CASCADE)
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Duration in hours for this employee")
    is_completed = models.BooleanField(default=False)
    assigned_date = models.DateTimeField(auto_now_add=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    receives_payment = models.BooleanField(default=True, help_text="Whether this employee receives payment for this workblock")

    class Meta:
        unique_together = ['employee', 'work_block']

    def __str__(self):
        return f"{self.employee.name} - {self.work_block} - {self.duration}h"

    def get_employee_hourly_rate(self):
        """Get the hourly rate for this employee - contract rate if available, otherwise workblock rate"""
        if self.employee.has_contract:
            return self.employee.contract_hourly_rate
        return self.work_block.hourly_value

    def get_employee_payment(self):
        """Get the total payment for this employee for this workblock"""
        if not self.receives_payment:
            return 0
        return self.duration * self.get_employee_hourly_rate()

    def get_client_cost(self):
        """Get the cost charged to the client for this employee's work"""
        return self.duration * self.work_block.hourly_value




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


class BonusPenalty(models.Model):
    BONUS = 'bonus'
    PENALTY = 'penalty'
    TYPE_CHOICES = [
        (BONUS, 'Bonus'),
        (PENALTY, 'Penalty'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='bonus_penalties')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount in euros")
    justification = models.TextField(help_text="Reason for bonus or penalty")
    month = models.IntegerField()
    year = models.IntegerField()
    created_date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"{self.get_type_display()} for {self.employee.name}: €{self.amount} ({self.month}/{self.year})"

    @property
    def signed_amount(self):
        """Return amount with appropriate sign for display"""
        if self.type == self.PENALTY:
            return -abs(self.amount)
        return abs(self.amount)
