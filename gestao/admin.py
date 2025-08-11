from django.contrib import admin
from .models import Employee, WorkBlock, Client, EmployeeWorkAssignment, BonusPenalty
from datetime import datetime, timedelta
from django.utils import timezone
import calendar

class EmployeeWorkAssignmentInline(admin.TabularInline):
    model = EmployeeWorkAssignment
    extra = 0
    fields = ('employee', 'duration', 'is_completed', 'completed_date', 'receives_payment', 'hourly_rate_override')
    readonly_fields = ('completed_date',)

class WorkBlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'day_of_month', 'month', 'year', 'start_time', 'end_time', 'localization', 'client', 'hourly_value', 'archived', 'constant')
    list_filter = ('archived', 'constant', 'client')
    inlines = [EmployeeWorkAssignmentInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Store info for save_related if this is a new constant block
        if obj.constant and not change:
            self._is_new_constant_block = True
            self._original_block = obj
        else:
            self._is_new_constant_block = False

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        # Only proceed if this was a new constant block
        if getattr(self, '_is_new_constant_block', False):
            obj = self._original_block
            date = datetime(obj.year, obj.month, obj.day_of_month)
            weekday = date.weekday()
            _, last_day = calendar.monthrange(obj.year, obj.month)

            for day in range(obj.day_of_month + 7, last_day + 1, 7):
                if date.weekday() == weekday and day <= last_day:
                    existing = WorkBlock.objects.filter(
                        name=obj.name,
                        day_of_month=day,
                        localization=obj.localization,
                        client=obj.client,
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
                            archived=obj.archived,
                            hourly_value=obj.hourly_value
                        )
                        # Copy assignments from original block (now they exist!)
                        for assignment in EmployeeWorkAssignment.objects.filter(work_block=obj):
                            EmployeeWorkAssignment.objects.create(
                                employee=assignment.employee,
                                work_block=new_block,
                                duration=assignment.duration,
                                receives_payment=assignment.receives_payment,
                                hourly_rate_override=assignment.hourly_rate_override
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

class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'contract_hourly_rate', 'has_contract')
    fields = ('name', 'user', 'contract_hourly_rate')

admin.site.register(Employee, EmployeeAdmin)
admin.site.register(WorkBlock, WorkBlockAdmin)
admin.site.register(Client)
admin.site.register(EmployeeWorkAssignment)
admin.site.register(BonusPenalty, BonusPenaltyAdmin)
