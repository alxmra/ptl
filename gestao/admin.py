from django.contrib import admin
from .models import Employee, WorkBlock, Client, EmployeeWorkAssignment, BonusPenalty
from datetime import datetime, timedelta
from django.utils import timezone
import calendar

class EmployeeWorkAssignmentInline(admin.TabularInline):
    model = EmployeeWorkAssignment
    extra = 0
    fields = ('employee', 'duration', 'is_completed', 'completed_date')
    readonly_fields = ('completed_date',)

class WorkBlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'day_of_month', 'month', 'year', 'start_time', 'end_time', 'localization', 'client', 'hourly_value', 'archived', 'constant')
    list_filter = ('archived', 'constant', 'client')
    inlines = [EmployeeWorkAssignmentInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.constant and not change:  # Only for new constant blocks
            date = datetime(obj.year, obj.month, obj.day_of_month)
            weekday = date.weekday()
            _, last_day = calendar.monthrange(obj.year, obj.month)
            for day in range(obj.day_of_month + 7, last_day + 1, 7):
                if date.weekday() == weekday and day <= last_day:
                    existing = WorkBlock.objects.filter(
                        day_of_month=day,
                        month=obj.month,
                        year=obj.year,
                        start_time=obj.start_time,
                        end_time=obj.end_time,
                        constant=True
                    ).exists()
                    if not existing:
                        new_block = WorkBlock.objects.create(
                            name=obj.name,
                            localization=obj.localization,
                            client=obj.client,
                            start_time=obj.start_time,
                            end_time=obj.end_time,
                            day_of_month=day,
                            month=obj.month,
                            year=obj.year,
                            duration=obj.duration,
                            constant=obj.constant,
                            archived=obj.archived
                        )
                        # Copy assignments from original block
                        for assignment in EmployeeWorkAssignment.objects.filter(work_block=obj):
                            EmployeeWorkAssignment.objects.create(
                                employee=assignment.employee,
                                work_block=new_block,
                                duration=assignment.duration
                            )

class BonusPenaltyAdmin(admin.ModelAdmin):
    list_display = ('employee', 'type', 'amount', 'month', 'year', 'created_date', 'created_by')
    list_filter = ('type', 'year', 'month', 'created_date')
    search_fields = ('employee__name', 'justification')
    readonly_fields = ('created_date', 'created_by')

    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by for new objects
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

admin.site.register(Employee)
admin.site.register(WorkBlock, WorkBlockAdmin)
admin.site.register(Client)
admin.site.register(EmployeeWorkAssignment)
admin.site.register(BonusPenalty, BonusPenaltyAdmin)
