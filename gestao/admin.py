from django.contrib import admin
from .models import Employee, WorkBlock, Client
from datetime import datetime, timedelta
from django.utils import timezone
import calendar

class WorkBlockAdmin(admin.ModelAdmin):
    list_display = ('name', 'day_of_month', 'month', 'year', 'start_time', 'end_time', 'localization', 'client', 'archived', 'constant')
    list_filter = ('archived', 'constant', 'client')
    filter_horizontal = ('employees_assigned', 'employees_concluded')

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
                        new_block.employees_assigned.set(obj.employees_assigned.all())

admin.site.register(Employee)
admin.site.register(WorkBlock, WorkBlockAdmin)
admin.site.register(Client)
