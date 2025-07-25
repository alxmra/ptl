from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import WorkBlock, Employee, EmployeeWorkAssignment, Client, BonusPenalty
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

import calendar
import csv
import json

def is_admin(user):
    return user.is_staff

def format_duration(decimal_hours):
    """Convert decimal hours to hours and minutes format (e.g., 15.50 -> "15h30m")"""
    if decimal_hours is None:
        return "0h"

    decimal_hours = Decimal(str(decimal_hours))
    hours = int(decimal_hours)
    minutes = int((decimal_hours - hours) * 60)

    if minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h{minutes:02d}m"

@login_required
@user_passes_test(is_admin)
def index(request, year=None, week=None):
    today = timezone.localtime(timezone.now()).date()

    # If no year/week provided, use current week
    # But if coming from navigation, keep the provided year/week
    if year is None or week is None:
        year, week = today.year, today.isocalendar()[1]

    # Ensure year and week are integers
    year = int(year)
    week = int(week)

    # Calculate start of the week (Monday)
    start_date = datetime.fromisocalendar(year, week, 1).date()
    end_date = start_date + timedelta(days=6)

    # Get all work blocks for the week (including archived ones for admin view)
    work_blocks = WorkBlock.objects.filter(
        year=year,
        month__in=[start_date.month, end_date.month]
    ).prefetch_related('employees_assigned', 'client')

    # Filter work blocks to only include those within the week
    week_blocks = []
    for block in work_blocks:
        block_date = datetime(block.year, block.month, block.day_of_month).date()
        if start_date <= block_date <= end_date:
            week_blocks.append(block)

    # Organize blocks by day with corrected positioning and overlap detection
    days = []
    time_slots = [(f"{h:02d}:00", f"{h:02d}:30") for h in range(6, 23)]  # 6 AM to 11 PM

    def blocks_overlap(block1, block2):
        """Check if two blocks have overlapping times"""
        start1 = block1.start_time.hour * 60 + block1.start_time.minute
        end1 = block1.end_time.hour * 60 + block1.end_time.minute
        start2 = block2.start_time.hour * 60 + block2.start_time.minute
        end2 = block2.end_time.hour * 60 + block2.end_time.minute

        return not (end1 <= start2 or end2 <= start1)

    for i in range(7):
        date = start_date + timedelta(days=i)
        day_blocks = [block for block in week_blocks if block.day_of_month == date.day and block.month == date.month]

        # Sort blocks by start time for consistent positioning
        day_blocks.sort(key=lambda b: (b.start_time, b.end_time))

        # Group overlapping blocks using a more robust algorithm
        overlap_groups = []
        for block in day_blocks:
            # Find all groups this block overlaps with
            overlapping_groups = []
            for group_idx, group in enumerate(overlap_groups):
                if any(blocks_overlap(block, existing_block) for existing_block in group):
                    overlapping_groups.append(group_idx)

            if not overlapping_groups:
                # Create new group
                overlap_groups.append([block])
            elif len(overlapping_groups) == 1:
                # Add to existing group
                overlap_groups[overlapping_groups[0]].append(block)
            else:
                # Merge multiple groups and add the block
                merged_group = [block]
                for group_idx in sorted(overlapping_groups, reverse=True):
                    merged_group.extend(overlap_groups.pop(group_idx))
                overlap_groups.append(merged_group)

        # Calculate positioning for each block
        positioned_blocks = []
        for group in overlap_groups:
            group_size = len(group)
            group_width = 90 / group_size  # Divide width among overlapping blocks with some margin

            # Sort group by start time for consistent left-to-right positioning
            group.sort(key=lambda b: (b.start_time, b.end_time))

            for idx, block in enumerate(group):
                # Calculate top position (minutes from 6 AM, converted to pixels)
                start_minutes = block.start_time.hour * 60 + block.start_time.minute
                top_position = 48 + ((start_minutes - 360) * (40/60))  # 48px for header, 360 minutes = 6 AM, 40px per hour (or 2/3 px per minute)

                # Calculate height (duration in minutes, converted to pixels)
                end_minutes = block.end_time.hour * 60 + block.end_time.minute
                duration_minutes = end_minutes - start_minutes
                height = max(duration_minutes * (40/60), 15)  # Minimum 15px height, scaled for 40px per hour

                # Calculate left position with small gaps between blocks
                left_position = 2 + (idx * (group_width + 1))  # 1% gap between blocks

                positioned_blocks.append({
                    'block': block,
                    'top': top_position,
                    'height': height,
                    'width': group_width,
                    'left': left_position,
                })

        days.append({'date': date, 'blocks': positioned_blocks})

    # Navigation - calculate based on the displayed week, not current week
    displayed_week_start = datetime.fromisocalendar(year, week, 1)
    prev_week_start = displayed_week_start - timedelta(days=7)
    next_week_start = displayed_week_start + timedelta(days=7)

    prev_week = prev_week_start.isocalendar()
    next_week = next_week_start.isocalendar()
    current_week = today.isocalendar()


    # Create block data for JavaScript
    block_data = {}
    for day in days:
        for block_data_item in day['blocks']:
            block = block_data_item['block']
            block_data[str(block.id)] = {
                'name': block.name or 'Work Block',
                'localization': block.localization or 'Not specified',
                'client': block.client.name if block.client else 'Outros',
                'start_time': block.start_time.strftime('%H:%M'),
                'end_time': block.end_time.strftime('%H:%M'),
                'duration': format_duration(block.duration),
                'hourly_value': float(block.hourly_value),
                'employees_assigned': [emp.name for emp in block.employees_assigned.all()],
                'employees_concluded': [emp.name for emp in block.get_employees_concluded()],
                'constant': block.constant,
                'archived': block.archived
            }

    context = {
        'days': days,
        'week_start': start_date,
        'week_end': end_date,
        'week_start_formatted': start_date.strftime("%B %d, %Y"),
        'week_end_formatted': end_date.strftime("%B %d, %Y"),
        'prev_week': {'year': prev_week[0], 'week': prev_week[1]},
        'next_week': {'year': next_week[0], 'week': next_week[1]},
        'current_week': {'year': current_week[0], 'week': current_week[1]},
        'time_slots': time_slots,
        'block_data_json': block_data,
    }

    # Check if this is an HTMX request for inner content
    if request.headers.get('HX-Request'):
        return render(request, 'gestao/admin_schedule_inner.html', context)
    else:
        return render(request, 'gestao/admin_schedule.html', context)

@login_required
def employee_tasks(request, year=None, week=None):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, 'gestao/employee_tasks.html', {'error': 'No employee profile associated with this user.'})

    today = timezone.localtime(timezone.now()).date()
    current_year, current_week = today.year, today.isocalendar()[1]

    # If no year/week provided, use current week
    if year is None or week is None:
        year, week = current_year, current_week

    # Ensure year and week are integers
    year = int(year)
    week = int(week)

    # Don't allow viewing weeks before current week
    if year < current_year or (year == current_year and week < current_week):
        year, week = current_year, current_week

    # Calculate start of the week (Monday)
    start_date = datetime.fromisocalendar(year, week, 1).date()
    end_date = start_date + timedelta(days=6)

    # Get all work blocks for the week where employee is assigned
    work_blocks = WorkBlock.objects.filter(
        archived=False,
        employees_assigned=employee,
        year=year,
        month__in=[start_date.month, end_date.month]
    ).prefetch_related('client')

    # Filter work blocks to only include those within the week
    week_blocks = []
    for block in work_blocks:
        block_date = datetime(block.year, block.month, block.day_of_month).date()
        if start_date <= block_date <= end_date:
            week_blocks.append(block)

    # Organize blocks by day with positioning similar to admin view
    days = []
    time_slots = [(f"{h:02d}:00", f"{h:02d}:30") for h in range(6, 23)]  # 6 AM to 11 PM

    def blocks_overlap(block1, block2):
        """Check if two blocks have overlapping times"""
        start1 = block1.start_time.hour * 60 + block1.start_time.minute
        end1 = block1.end_time.hour * 60 + block1.end_time.minute
        start2 = block2.start_time.hour * 60 + block2.start_time.minute
        end2 = block2.end_time.hour * 60 + block2.end_time.minute
        return not (end1 <= start2 or end2 <= start1)

    for i in range(7):
        date = start_date + timedelta(days=i)
        day_blocks = [block for block in week_blocks if block.day_of_month == date.day and block.month == date.month]

        # Sort blocks by start time for consistent positioning
        day_blocks.sort(key=lambda b: (b.start_time, b.end_time))

        # Group overlapping blocks
        overlap_groups = []
        for block in day_blocks:
            overlapping_groups = []
            for group_idx, group in enumerate(overlap_groups):
                if any(blocks_overlap(block, existing_block) for existing_block in group):
                    overlapping_groups.append(group_idx)

            if not overlapping_groups:
                overlap_groups.append([block])
            elif len(overlapping_groups) == 1:
                overlap_groups[overlapping_groups[0]].append(block)
            else:
                merged_group = [block]
                for group_idx in sorted(overlapping_groups, reverse=True):
                    merged_group.extend(overlap_groups.pop(group_idx))
                overlap_groups.append(merged_group)

        # Calculate positioning for each block
        positioned_blocks = []
        for group in overlap_groups:
            group_size = len(group)
            group_width = 90 / group_size

            group.sort(key=lambda b: (b.start_time, b.end_time))

            for idx, block in enumerate(group):
                start_minutes = block.start_time.hour * 60 + block.start_time.minute
                top_position = 48 + ((start_minutes - 360) * (40/60))

                end_minutes = block.end_time.hour * 60 + block.end_time.minute
                duration_minutes = end_minutes - start_minutes
                height = max(duration_minutes * (40/60), 15)

                left_position = 2 + (idx * (group_width + 1))

                positioned_blocks.append({
                    'block': block,
                    'top': top_position,
                    'height': height,
                    'width': group_width,
                    'left': left_position,
                    'employee_duration': block.get_employee_duration(employee),
                    'is_completed': block.is_employee_completed(employee),
                })

        days.append({'date': date, 'blocks': positioned_blocks})

    # Navigation
    displayed_week_start = datetime.fromisocalendar(year, week, 1)
    next_week_start = displayed_week_start + timedelta(days=7)
    prev_week_start = displayed_week_start - timedelta(days=7)

    next_week = next_week_start.isocalendar()
    prev_week = prev_week_start.isocalendar()

    # Only show previous week if it's not before current week
    show_prev = prev_week[0] > current_year or (prev_week[0] == current_year and prev_week[1] >= current_week)

    # Create block data for JavaScript
    block_data = {}
    for day in days:
        for block_data_item in day['blocks']:
            block = block_data_item['block']
            block_data[str(block.id)] = {
                'name': block.name or 'Work Block',
                'localization': block.localization or 'Not specified',
                'client': block.client.name if block.client else 'Outros',
                'start_time': block.start_time.strftime('%H:%M'),
                'end_time': block.end_time.strftime('%H:%M'),
                'duration': format_duration(block_data_item['employee_duration']),
                'duration_numeric': float(block_data_item['employee_duration']),
                'default_duration': format_duration(block.duration),
                'archived': block.archived,
                'is_completed': block_data_item['is_completed'],
                'can_edit': year == current_year and week >= current_week,
            }

    context = {
        'days': days,
        'week_start': start_date,
        'week_end': end_date,
        'week_start_formatted': start_date.strftime("%B %d, %Y"),
        'week_end_formatted': end_date.strftime("%B %d, %Y"),
        'prev_week': {'year': prev_week[0], 'week': prev_week[1]},
        'next_week': {'year': next_week[0], 'week': next_week[1]},
        'current_week': {'year': current_year, 'week': current_week},
        'show_prev': show_prev,
        'time_slots': time_slots,
        'block_data_json': block_data,
        'employee': employee,
    }

    # Check if this is an HTMX request
    if request.headers.get('HX-Request'):
        return render(request, 'gestao/employee_schedule_inner.html', context)
    else:
        return render(request, 'gestao/employee_schedule.html', context)

@login_required
@require_POST
def toggle_completion(request, block_id):
    try:
        employee = Employee.objects.get(user=request.user)
        work_block = WorkBlock.objects.get(id=block_id)

        # Check if employee is assigned to this block
        if not work_block.employees_assigned.filter(id=employee.id).exists():
            return JsonResponse({'error': 'Not authorized'}, status=403)

        # Get or create assignment
        assignment, created = EmployeeWorkAssignment.objects.get_or_create(
            employee=employee,
            work_block=work_block,
            defaults={'duration': work_block.duration}
        )

        # Toggle completion
        assignment.is_completed = not assignment.is_completed
        if assignment.is_completed:
            assignment.completed_date = timezone.now()
        else:
            assignment.completed_date = None
        assignment.save()

        return JsonResponse({
            'success': True,
            'is_completed': assignment.is_completed,
            'completed_date': assignment.completed_date.isoformat() if assignment.completed_date else None
        })

    except (Employee.DoesNotExist, WorkBlock.DoesNotExist):
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def update_duration(request, block_id):
    try:
        employee = Employee.objects.get(user=request.user)
        work_block = WorkBlock.objects.get(id=block_id)

        # Check if employee is assigned to this block
        if not work_block.employees_assigned.filter(id=employee.id).exists():
            return JsonResponse({'error': 'Not authorized'}, status=403)

        # Check if the week has passed (can't edit past weeks)
        today = timezone.localtime(timezone.now()).date()
        current_year, current_week = today.year, today.isocalendar()[1]

        block_date = datetime(work_block.year, work_block.month, work_block.day_of_month).date()
        block_year, block_week = block_date.isocalendar()[:2]

        if block_year < current_year or (block_year == current_year and block_week < current_week):
            return JsonResponse({'error': 'Cannot edit past weeks'}, status=403)

        # Get new duration from request
        try:
            from decimal import Decimal
            new_duration = Decimal(request.POST.get('duration', 0))
            if new_duration <= 0:
                return JsonResponse({'error': 'Duration must be positive'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid duration format'}, status=400)

        # Get or create assignment
        assignment, created = EmployeeWorkAssignment.objects.get_or_create(
            employee=employee,
            work_block=work_block,
            defaults={'duration': work_block.duration}
        )

        # Update duration
        assignment.duration = new_duration
        assignment.save()

        return JsonResponse({
            'success': True,
            'duration': float(assignment.duration),
            'duration_formatted': format_duration(assignment.duration)
        })

    except (Employee.DoesNotExist, WorkBlock.DoesNotExist):
        return JsonResponse({'error': 'Not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_admin)
def admin_statistics(request, year=None, month=None):
    today = timezone.localtime(timezone.now()).date()

    # If no year/month provided, use current month
    if year is None or month is None:
        year, month = today.year, today.month

    # Ensure year and month are integers
    year = int(year)
    month = int(month)

    # Handle CSV export
    export_type = request.GET.get('export')
    if export_type:
        return handle_csv_export(request, year, month, export_type)

    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()

    # Get all work blocks for the month
    work_blocks = WorkBlock.objects.filter(
        year=year,
        month=month,
        archived=False
    ).prefetch_related('employees_assigned', 'client')

    # Employee statistics
    employee_stats = []
    for employee in Employee.objects.all():
        # Get completed assignments for this employee in this month
        completed_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block')

        # Get ALL assignments for this employee in this month (for expected hours calculation)
        all_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False
        ).select_related('work_block')

        # Get assigned assignments for current week within the selected month
        # Only show current week data if today falls within the selected month
        current_week_filtered = []
        if today.year == year and today.month == month:
            current_week_start = today - timedelta(days=today.weekday())
            current_week_end = current_week_start + timedelta(days=6)

            current_week_assignments = EmployeeWorkAssignment.objects.filter(
                employee=employee,
                work_block__year=year,
                work_block__month=month,
                work_block__archived=False
            ).select_related('work_block')

            # Filter for current week within the selected month
            for assignment in current_week_assignments:
                block_date = datetime(assignment.work_block.year, assignment.work_block.month, assignment.work_block.day_of_month).date()
                if current_week_start <= block_date <= current_week_end:
                    current_week_filtered.append(assignment)

        # Calculate statistics
        # Hours worked: Only completed tasks (is_completed=True)
        total_hours_worked = sum(assignment.duration for assignment in completed_assignments)

        # Value earned: Only based on completed hours × employee rate (contract or workblock) and only if receives_payment=True
        total_value_earned = sum(assignment.get_employee_payment() for assignment in completed_assignments)

        # Get bonuses and penalties for this employee in this month
        bonuses_penalties = BonusPenalty.objects.filter(
            employee=employee,
            year=year,
            month=month
        ).order_by('-created_date')

        # Calculate bonus/penalty adjustments
        bonus_penalty_total = sum(bp.signed_amount for bp in bonuses_penalties)
        final_value_earned = total_value_earned + bonus_penalty_total

        current_week_hours_assigned = sum(assignment.duration for assignment in current_week_filtered)
        current_week_blocks_assigned = len(current_week_filtered)

        # Expected hours: ALL assigned tasks (completed + pending) - represents total workload
        expected_hours = sum(assignment.duration for assignment in all_assignments)

        # Group completed assignments by day for detailed view
        daily_work = {}
        for assignment in completed_assignments:
            day = assignment.work_block.day_of_month
            if day not in daily_work:
                daily_work[day] = {
                    'date': datetime(year, month, day).date(),
                    'total_hours': 0,
                    'assignments': []
                }
            daily_work[day]['total_hours'] += assignment.duration
            daily_work[day]['assignments'].append(assignment)

        # Sort by day
        sorted_daily_work = sorted(daily_work.items(), key=lambda x: x[0])

        employee_stats.append({
            'employee': employee,
            'total_hours_worked': total_hours_worked,
            'total_value_earned': total_value_earned,
            'final_value_earned': final_value_earned,
            'bonus_penalty_total': bonus_penalty_total,
            'bonuses_penalties': bonuses_penalties,
            'has_bonus_penalty': bonuses_penalties.exists(),
            'current_week_hours_assigned': current_week_hours_assigned,
            'current_week_blocks_assigned': current_week_blocks_assigned,
            'expected_hours': expected_hours,
            'completed_assignments': completed_assignments,
            'daily_work': sorted_daily_work,
        })

    # Client statistics
    client_stats = []

    # Get all clients plus handle "Outros" for null clients
    client_ids = list(work_blocks.values_list('client', flat=True).distinct())
    has_null_client = None in client_ids

    # Process regular clients
    for client_id in client_ids:
        if client_id is None:
            continue

        client_obj = work_blocks.filter(client=client_id).first().client

        # Get completed work for this client in this month
        client_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=client_id,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in client_completed_assignments)
        total_value = sum(assignment.get_client_cost() for assignment in client_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in client_completed_assignments))

        # Group assignments by day for detailed view
        daily_work = {}
        for assignment in client_completed_assignments:
            day = assignment.work_block.day_of_month
            if day not in daily_work:
                daily_work[day] = {
                    'date': datetime(year, month, day).date(),
                    'assignments': []
                }
            daily_work[day]['assignments'].append(assignment)

        # Sort by day
        sorted_daily_work = sorted(daily_work.items(), key=lambda x: x[0])

        client_stats.append({
            'client': client_obj,
            'total_hours': total_hours,
            'total_value': total_value,
            'unique_workers': unique_workers,
            'completed_assignments': client_completed_assignments,
            'daily_work': sorted_daily_work,
        })

    # Handle "Outros" client for null clients
    if has_null_client:
        # Create a fake client object for "Outros"
        class OutrosClient:
            def __init__(self):
                self.id = 'outros'
                self.name = 'Outros'

        outros_client = OutrosClient()

        # Get completed work for null client (Outros) in this month
        outros_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=None,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in outros_completed_assignments)
        total_value = sum(assignment.get_client_cost() for assignment in outros_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in outros_completed_assignments))

        # Group assignments by day for detailed view
        daily_work = {}
        for assignment in outros_completed_assignments:
            day = assignment.work_block.day_of_month
            if day not in daily_work:
                daily_work[day] = {
                    'date': datetime(year, month, day).date(),
                    'assignments': []
                }
            daily_work[day]['assignments'].append(assignment)

        # Sort by day
        sorted_daily_work = sorted(daily_work.items(), key=lambda x: x[0])

        client_stats.append({
            'client': outros_client,
            'total_hours': total_hours,
            'total_value': total_value,
            'unique_workers': unique_workers,
            'completed_assignments': outros_completed_assignments,
            'daily_work': sorted_daily_work,
        })

    # Navigation
    prev_month = first_day - timedelta(days=1)
    next_month = last_day + timedelta(days=1)

    # Prepare chart data for JavaScript
    employee_chart_data = []
    for stat in employee_stats:
        daily_hours = {}
        for day, day_data in stat['daily_work']:
            daily_hours[day] = float(day_data['total_hours'])

        employee_chart_data.append({
            'id': stat['employee'].id,
            'name': stat['employee'].name,
            'daily_hours': daily_hours
        })

    client_chart_data = []
    for stat in client_stats:
        daily_hours = {}
        for day, day_data in stat['daily_work']:
            total_hours = sum(float(assignment.duration) for assignment in day_data['assignments'])
            daily_hours[day] = total_hours

        client_chart_data.append({
            'id': stat['client'].id,
            'name': stat['client'].name,
            'daily_hours': daily_hours
        })

    context = {
        'employee_stats': employee_stats,
        'client_stats': client_stats,
        'employee_chart_data': json.dumps(employee_chart_data),
        'client_chart_data': json.dumps(client_chart_data),
        'current_month': first_day,
        'month_name': calendar.month_name[month],
        'year': year,
        'month': month,
        'prev_month': {'year': prev_month.year, 'month': prev_month.month},
        'next_month': {'year': next_month.year, 'month': next_month.month},
        'current_week_start': today - timedelta(days=today.weekday()),
        'current_week_end': today - timedelta(days=today.weekday()) + timedelta(days=6),
    }

    return render(request, 'gestao/admin_statistics.html', context)

def handle_csv_export(request, year, month, export_type):
    """Handle CSV export for different data types"""
    today = timezone.localtime(timezone.now()).date()

    # Get first and last day of the month
    first_day = datetime(year, month, 1).date()
    last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()
    month_name = calendar.month_name[month]

    # Get all work blocks for the month
    work_blocks = WorkBlock.objects.filter(
        year=year,
        month=month,
        archived=False
    ).prefetch_related('employees_assigned', 'client')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ptl_statistics_{month_name}_{year}_{export_type}.csv"'

    writer = csv.writer(response)

    if export_type == 'employee_csv':
        return export_employee_csv(writer, year, month, month_name, today)
    elif export_type == 'client_csv':
        return export_client_csv(writer, year, month, month_name)
    elif export_type == 'combined_csv':
        return export_combined_csv(writer, year, month, month_name, today)

    return response

def export_employee_csv(writer, year, month, month_name, today):
    """Export employee statistics to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ptl_employee_statistics_{month_name}_{year}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow([
        'Employee Name',
        f'Hours Worked ({month_name})',
        'Expected Hours',
        f'Value Earned ({month_name})',
        'Current Week Blocks',
        'Current Week Hours'
    ])

    # Get employee statistics
    for employee in Employee.objects.all():
        # Get completed assignments for this employee in this month
        completed_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block')

        # Get ALL assignments for this employee in this month (for expected hours calculation)
        all_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False
        ).select_related('work_block')

        # Get assigned assignments for current week within the selected month
        current_week_filtered = []
        if today.year == year and today.month == month:
            current_week_start = today - timedelta(days=today.weekday())
            current_week_end = current_week_start + timedelta(days=6)

            current_week_assignments = EmployeeWorkAssignment.objects.filter(
                employee=employee,
                work_block__year=year,
                work_block__month=month,
                work_block__archived=False
            ).select_related('work_block')

            # Filter for current week within the selected month
            for assignment in current_week_assignments:
                block_date = datetime(assignment.work_block.year, assignment.work_block.month, assignment.work_block.day_of_month).date()
                if current_week_start <= block_date <= current_week_end:
                    current_week_filtered.append(assignment)

        # Calculate statistics
        # Hours worked: Only completed tasks (is_completed=True)
        total_hours_worked = sum(assignment.duration for assignment in completed_assignments)

        # Value earned: Only based on completed hours × hourly rate
        total_value_earned = sum(assignment.duration * assignment.work_block.hourly_value for assignment in completed_assignments)

        current_week_hours_assigned = sum(assignment.duration for assignment in current_week_filtered)
        current_week_blocks_assigned = len(current_week_filtered)

        # Expected hours: ALL assigned tasks (completed + pending) - represents total workload
        expected_hours = sum(assignment.duration for assignment in all_assignments)

        writer.writerow([
            employee.name,
            f"{float(total_hours_worked):.2f}",
            f"{float(expected_hours):.2f}",
            f"{float(total_value_earned):.2f}",
            current_week_blocks_assigned,
            f"{float(current_week_hours_assigned):.2f}"
        ])

    return response

def export_client_csv(writer, year, month, month_name):
    """Export client statistics to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ptl_client_statistics_{month_name}_{year}.csv"'

    writer = csv.writer(response)

    # Write header
    writer.writerow([
        'Client Name',
        f'Hours Worked ({month_name})',
        'Total Value',
        'Workers Count'
    ])

    # Get work blocks for the month
    work_blocks = WorkBlock.objects.filter(
        year=year,
        month=month,
        archived=False
    ).prefetch_related('employees_assigned', 'client')

    # Get all clients plus handle "Outros" for null clients
    client_ids = list(work_blocks.values_list('client', flat=True).distinct())
    has_null_client = None in client_ids

    # Process regular clients
    for client_id in client_ids:
        if client_id is None:
            continue

        client_obj = work_blocks.filter(client=client_id).first().client

        # Get completed work for this client in this month
        client_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=client_id,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in client_completed_assignments)
        total_value = sum(assignment.duration * assignment.work_block.hourly_value for assignment in client_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in client_completed_assignments))

        writer.writerow([
            client_obj.name,
            f"{float(total_hours):.2f}",
            f"{float(total_value):.2f}",
            unique_workers
        ])

    # Handle "Outros" client for null clients
    if has_null_client:
        # Get completed work for null client (Outros) in this month
        outros_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=None,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in outros_completed_assignments)
        total_value = sum(assignment.duration * assignment.work_block.hourly_value for assignment in outros_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in outros_completed_assignments))

        writer.writerow([
            'Outros',
            f"{float(total_hours):.2f}",
            f"{float(total_value):.2f}",
            unique_workers
        ])

    return response

def export_combined_csv(writer, year, month, month_name, today):
    """Export combined employee and client statistics to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="ptl_combined_statistics_{month_name}_{year}.csv"'

    writer = csv.writer(response)

    # Write employee section
    writer.writerow(['EMPLOYEE STATISTICS'])
    writer.writerow([
        'Employee Name',
        f'Hours Worked ({month_name})',
        'Expected Hours',
        f'Value Earned ({month_name})',
        'Current Week Blocks',
        'Current Week Hours'
    ])

    # Get employee statistics (similar to export_employee_csv)
    for employee in Employee.objects.all():
        completed_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block')

        # Get ALL assignments for this employee in this month (for expected hours calculation)
        all_assignments = EmployeeWorkAssignment.objects.filter(
            employee=employee,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False
        ).select_related('work_block')

        current_week_filtered = []
        if today.year == year and today.month == month:
            current_week_start = today - timedelta(days=today.weekday())
            current_week_end = current_week_start + timedelta(days=6)

            current_week_assignments = EmployeeWorkAssignment.objects.filter(
                employee=employee,
                work_block__year=year,
                work_block__month=month,
                work_block__archived=False
            ).select_related('work_block')

            for assignment in current_week_assignments:
                block_date = datetime(assignment.work_block.year, assignment.work_block.month, assignment.work_block.day_of_month).date()
                if current_week_start <= block_date <= current_week_end:
                    current_week_filtered.append(assignment)

        # Calculate statistics
        # Hours worked: Only completed tasks (is_completed=True)
        total_hours_worked = sum(assignment.duration for assignment in completed_assignments)

        # Value earned: Only based on completed hours × hourly rate
        total_value_earned = sum(assignment.duration * assignment.work_block.hourly_value for assignment in completed_assignments)

        current_week_hours_assigned = sum(assignment.duration for assignment in current_week_filtered)
        current_week_blocks_assigned = len(current_week_filtered)

        # Expected hours: ALL assigned tasks (completed + pending) - represents total workload
        expected_hours = sum(assignment.duration for assignment in all_assignments)

        writer.writerow([
            employee.name,
            f"{float(total_hours_worked):.2f}",
            f"{float(expected_hours):.2f}",
            f"{float(total_value_earned):.2f}",
            current_week_blocks_assigned,
            f"{float(current_week_hours_assigned):.2f}"
        ])

    # Add empty row
    writer.writerow([])

    # Write client section
    writer.writerow(['CLIENT STATISTICS'])
    writer.writerow([
        'Client Name',
        f'Hours Worked ({month_name})',
        'Total Value',
        'Workers Count'
    ])

    # Get work blocks for the month
    work_blocks = WorkBlock.objects.filter(
        year=year,
        month=month,
        archived=False
    ).prefetch_related('employees_assigned', 'client')

    # Get all clients plus handle "Outros" for null clients
    client_ids = list(work_blocks.values_list('client', flat=True).distinct())
    has_null_client = None in client_ids

    # Process regular clients
    for client_id in client_ids:
        if client_id is None:
            continue

        client_obj = work_blocks.filter(client=client_id).first().client

        client_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=client_id,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in client_completed_assignments)
        total_value = sum(assignment.duration * assignment.work_block.hourly_value for assignment in client_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in client_completed_assignments))

        writer.writerow([
            client_obj.name,
            f"{float(total_hours):.2f}",
            f"{float(total_value):.2f}",
            unique_workers
        ])

    # Handle "Outros" client
    if has_null_client:
        outros_completed_assignments = EmployeeWorkAssignment.objects.filter(
            work_block__client=None,
            work_block__year=year,
            work_block__month=month,
            work_block__archived=False,
            is_completed=True
        ).select_related('work_block', 'employee')

        total_hours = sum(assignment.duration for assignment in outros_completed_assignments)
        total_value = sum(assignment.duration * assignment.work_block.hourly_value for assignment in outros_completed_assignments)
        unique_workers = len(set(assignment.employee for assignment in outros_completed_assignments))

        writer.writerow([
            'Outros',
            f"{float(total_hours):.2f}",
            f"{float(total_value):.2f}",
            unique_workers
        ])

    return response

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect('admin_schedule')
            return redirect('employee_schedule')
        else:
            return render(request, 'gestao/login.html', {'error': 'Invalid credentials'})
    return render(request, 'gestao/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
@user_passes_test(is_admin)
def api_employees(request):
    """API endpoint to get all employees"""
    employees = Employee.objects.all()
    employee_data = [
        {
            'id': emp.id,
            'name': emp.name,
        }
        for emp in employees
    ]
    return JsonResponse(employee_data, safe=False)

@login_required
@user_passes_test(is_admin)
def api_work_block_assignments(request, block_id):
    """API endpoint to get work block assignments"""
    try:
        work_block = WorkBlock.objects.get(id=block_id)
        assignments = EmployeeWorkAssignment.objects.filter(work_block=work_block)

        assigned_employees = [assignment.employee.name for assignment in assignments]

        return JsonResponse({
            'success': True,
            'assigned_employees': assigned_employees,
            'block_name': work_block.name or 'Work Block',
            'block_details': f"{work_block.start_time} - {work_block.end_time}"
        })
    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@login_required
@user_passes_test(is_admin)
def api_assign_employees(request):
    """API endpoint to assign employees to work block"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        block_id = data.get('block_id')
        employee_names = data.get('employee_names', [])

        if not block_id:
            return JsonResponse({'success': False, 'error': 'Block ID is required'}, status=400)

        # Get the work block
        work_block = WorkBlock.objects.get(id=block_id)

        # Clear existing assignments
        EmployeeWorkAssignment.objects.filter(work_block=work_block).delete()

        # Create new assignments
        for employee_name in employee_names:
            try:
                employee = Employee.objects.get(name=employee_name)
                EmployeeWorkAssignment.objects.create(
                    employee=employee,
                    work_block=work_block,
                    duration=work_block.duration,
                    is_completed=False
                )
            except Employee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Employee "{employee_name}" not found'
                }, status=400)

        return JsonResponse({
            'success': True,
            'message': f'Successfully assigned {len(employee_names)} employees to work block'
        })

    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_delete_work_block(request, block_id):
    """API endpoint to delete a work block"""
    if request.method != 'DELETE':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        work_block = WorkBlock.objects.get(id=block_id)
        work_block.delete()
        return JsonResponse({'success': True, 'message': 'Work block deleted successfully'})
    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_toggle_archive_work_block(request, block_id):
    """API endpoint to archive/unarchive a work block"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        work_block = WorkBlock.objects.get(id=block_id)
        work_block.archived = not work_block.archived
        work_block.save()

        status = 'archived' if work_block.archived else 'unarchived'
        return JsonResponse({
            'success': True,
            'message': f'Work block {status} successfully',
            'archived': work_block.archived
        })
    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_edit_work_block(request, block_id):
    """API endpoint to edit a work block"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        work_block = WorkBlock.objects.get(id=block_id)

        # Update basic fields
        work_block.name = data.get('name', work_block.name)
        work_block.localization = data.get('localization', work_block.localization)
        work_block.start_time = data.get('start_time', work_block.start_time)
        work_block.end_time = data.get('end_time', work_block.end_time)
        work_block.duration = data.get('duration', work_block.duration)
        work_block.hourly_value = data.get('hourly_value', work_block.hourly_value)

        # Update client if provided
        client_name = data.get('client')
        if client_name:
            try:
                client = Client.objects.get(name=client_name)
                work_block.client = client
            except Client.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Client "{client_name}" not found'}, status=400)

        work_block.save()

        # Handle employee assignments and completions
        employee_data = data.get('employees', [])

        # Clear existing assignments
        EmployeeWorkAssignment.objects.filter(work_block=work_block).delete()

        # Create new assignments
        for emp_data in employee_data:
            try:
                employee = Employee.objects.get(name=emp_data['name'])
                EmployeeWorkAssignment.objects.create(
                    employee=employee,
                    work_block=work_block,
                    duration=emp_data.get('duration', work_block.duration),
                    is_completed=emp_data.get('is_completed', False),
                    receives_payment=emp_data.get('receives_payment', True),
                    hourly_rate_override=emp_data.get('hourly_rate_override')
                )
            except Employee.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': f'Employee "{emp_data["name"]}" not found'
                }, status=400)

        return JsonResponse({
            'success': True,
            'message': 'Work block updated successfully'
        })

    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def api_get_work_block_details(request, block_id):
    """API endpoint to get detailed work block information for editing"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        work_block = WorkBlock.objects.get(id=block_id)

        # Get all clients for dropdown
        clients = list(Client.objects.values_list('name', flat=True))

        # Get current assignments
        assignments = EmployeeWorkAssignment.objects.filter(work_block=work_block)
        employee_assignments = []
        for assignment in assignments:
            employee_assignments.append({
                'name': assignment.employee.name,
                'duration': float(assignment.duration),
                'is_completed': assignment.is_completed,
                'receives_payment': assignment.receives_payment,
                'contract_hourly_rate': float(assignment.employee.contract_hourly_rate) if assignment.employee.contract_hourly_rate else None,
                'has_contract': assignment.employee.has_contract,
                'hourly_rate_override': float(assignment.hourly_rate_override) if assignment.hourly_rate_override else None,
                'effective_hourly_rate': float(assignment.get_employee_hourly_rate())
            })

        return JsonResponse({
            'success': True,
            'work_block': {
                'id': work_block.id,
                'name': work_block.name,
                'localization': work_block.localization,
                'client': work_block.client.name if work_block.client else '',
                'start_time': work_block.start_time.strftime('%H:%M'),
                'end_time': work_block.end_time.strftime('%H:%M'),
                'duration': float(work_block.duration),
                'hourly_value': float(work_block.hourly_value),
                'archived': work_block.archived,
                'employees': employee_assignments
            },
            'clients': clients
        })

    except WorkBlock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Work block not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
@require_POST
@csrf_exempt
def api_add_bonus_penalty(request):
    """Add a bonus or penalty for an employee"""
    try:
        import json
        data = json.loads(request.body)

        employee_id = data.get('employee_id')
        type_value = data.get('type')  # 'bonus' or 'penalty'
        amount = data.get('amount')
        justification = data.get('justification')
        month = data.get('month')
        year = data.get('year')

        # Validate required fields
        if not all([employee_id, type_value, amount, justification, month, year]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

        if type_value not in ['bonus', 'penalty']:
            return JsonResponse({'success': False, 'error': 'Invalid type. Must be "bonus" or "penalty"'}, status=400)

        try:
            amount = Decimal(str(amount))
            if amount <= 0:
                return JsonResponse({'success': False, 'error': 'Amount must be positive'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)

        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Employee not found'}, status=404)

        # Create the bonus/penalty
        bonus_penalty = BonusPenalty.objects.create(
            employee=employee,
            type=type_value,
            amount=amount,
            justification=justification,
            month=int(month),
            year=int(year),
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'bonus_penalty': {
                'id': bonus_penalty.id,
                'type': bonus_penalty.type,
                'amount': float(bonus_penalty.amount),
                'signed_amount': float(bonus_penalty.signed_amount),
                'justification': bonus_penalty.justification,
                'created_date': bonus_penalty.created_date.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': bonus_penalty.created_by.username if bonus_penalty.created_by else 'Unknown'
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
def api_get_employee_bonuses_penalties(request, employee_id):
    """Get all bonuses and penalties for an employee in a specific month/year"""
    try:
        month = request.GET.get('month')
        year = request.GET.get('year')

        if not month or not year:
            return JsonResponse({'success': False, 'error': 'Month and year are required'}, status=400)

        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Employee not found'}, status=404)

        bonuses_penalties = BonusPenalty.objects.filter(
            employee=employee,
            month=int(month),
            year=int(year)
        ).order_by('-created_date')

        data = []
        for bp in bonuses_penalties:
            data.append({
                'id': bp.id,
                'type': bp.type,
                'amount': float(bp.amount),
                'signed_amount': float(bp.signed_amount),
                'justification': bp.justification,
                'created_date': bp.created_date.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': bp.created_by.username if bp.created_by else 'Unknown'
            })

        return JsonResponse({
            'success': True,
            'employee_name': employee.name,
            'bonuses_penalties': data,
            'total_adjustment': float(sum(bp.signed_amount for bp in bonuses_penalties))
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
@require_POST
@csrf_exempt
def api_delete_bonus_penalty(request, bonus_penalty_id):
    """Delete a bonus or penalty entry"""
    try:
        try:
            bonus_penalty = BonusPenalty.objects.get(id=bonus_penalty_id)
        except BonusPenalty.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Bonus/Penalty not found'}, status=404)

        # Store info before deletion for response
        employee_name = bonus_penalty.employee.name
        type_name = bonus_penalty.get_type_display()
        amount = float(bonus_penalty.amount)

        # Delete the bonus/penalty
        bonus_penalty.delete()

        return JsonResponse({
            'success': True,
            'message': f'{type_name} of €{amount:.2f} for {employee_name} has been deleted'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
@require_POST
@csrf_exempt
def api_toggle_assignment_payment(request, assignment_id):
    """Toggle payment status for an employee work assignment"""
    try:
        data = json.loads(request.body)
        receives_payment = data.get('receives_payment', True)

        try:
            assignment = EmployeeWorkAssignment.objects.get(id=assignment_id)
        except EmployeeWorkAssignment.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Assignment not found'}, status=404)

        # Update payment status
        assignment.receives_payment = receives_payment
        assignment.save()

        return JsonResponse({
            'success': True,
            'message': f'Payment status updated for {assignment.employee.name}'
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@user_passes_test(is_admin)
@require_POST
@csrf_exempt
def api_update_assignment_hourly_rate(request, assignment_id):
    """Update hourly rate override for an employee work assignment"""
    try:
        data = json.loads(request.body)
        hourly_rate_override = data.get('hourly_rate_override')

        try:
            assignment = EmployeeWorkAssignment.objects.get(id=assignment_id)
        except EmployeeWorkAssignment.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Assignment not found'}, status=404)

        # Update hourly rate override
        assignment.hourly_rate_override = hourly_rate_override
        assignment.save()

        return JsonResponse({
            'success': True,
            'message': f'Hourly rate updated for {assignment.employee.name}',
            'effective_rate': float(assignment.get_employee_hourly_rate())
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
