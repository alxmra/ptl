from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import WorkBlock, Employee
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth import authenticate, login, logout

def is_admin(user):
    return user.is_staff

@login_required
@user_passes_test(is_admin)
def index(request, year=None, week=None):
    today = timezone.localtime(timezone.now()).date()
    if year is None or week is None:
        year, week = today.year, today.isocalendar()[1]

    # Calculate start of the week (Monday)
    start_date = datetime.fromisocalendar(year, week, 1).date()
    end_date = start_date + timedelta(days=6)

    # Get all work blocks for the week
    work_blocks = WorkBlock.objects.filter(
        archived=False,
        year=year,
        month__in=[start_date.month, end_date.month]
    ).prefetch_related('employees_assigned', 'employees_concluded', 'client')

    # Filter work blocks to only include those within the week
    week_blocks = []
    for block in work_blocks:
        block_date = datetime(block.year, block.month, block.day_of_month).date()
        if start_date <= block_date <= end_date:
            week_blocks.append(block)

    # Organize blocks by day with corrected positioning and overlap detection
    days = []
    time_slots = [(f"{h:02d}:00", f"{h:02d}:30") for h in range(6, 22)]  # 6 AM to 10 PM
    
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
        day_blocks.sort(key=lambda b: b.start_time)
        
        # Group overlapping blocks
        overlap_groups = []
        for block in day_blocks:
            # Find which group this block belongs to
            placed = False
            for group in overlap_groups:
                if any(blocks_overlap(block, existing_block) for existing_block in group):
                    group.append(block)
                    placed = True
                    break
            if not placed:
                overlap_groups.append([block])
        
        # Calculate positioning for each block
        positioned_blocks = []
        for group in overlap_groups:
            group_width = 95 / len(group)  # Divide width among overlapping blocks
            for idx, block in enumerate(group):
                # Calculate top position (minutes from 6 AM, converted to pixels)
                start_minutes = block.start_time.hour * 60 + block.start_time.minute
                top_position = 48 + ((start_minutes - 360) * 0.5)  # 48px for header, 360 minutes = 6 AM, 0.5px per minute
                
                # Calculate height (duration in minutes, converted to pixels)
                end_minutes = block.end_time.hour * 60 + block.end_time.minute
                duration_minutes = end_minutes - start_minutes
                height = duration_minutes * 0.5  # 0.5px per minute
                
                positioned_blocks.append({
                    'block': block,
                    'top': top_position,
                    'height': height,
                    'width': group_width,
                    'left': 2.5 + (idx * group_width),  # Position side by side
                })
        
        days.append({'date': date, 'blocks': positioned_blocks})

    # Navigation
    prev_week = (datetime.fromisocalendar(year, week, 1) - timedelta(days=7)).isocalendar()
    next_week = (datetime.fromisocalendar(year, week, 1) + timedelta(days=7)).isocalendar()
    current_week = today.isocalendar()

    context = {
        'days': days,
        'week_start': start_date,
        'week_end': end_date,
        'prev_week': {'year': prev_week[0], 'week': prev_week[1]},
        'next_week': {'year': next_week[0], 'week': next_week[1]},
        'current_week': {'year': current_week[0], 'week': current_week[1]},
        'time_slots': time_slots,
    }
    return render(request, 'gestao/admin_schedule.html', context)

@login_required
def employee_tasks(request):
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return render(request, 'gestao/employee_tasks.html', {'error': 'No employee profile associated with this user.'})

    today = timezone.localtime(timezone.now()).date()
    year, week = today.year, today.isocalendar()[1]
    start_date = datetime.fromisocalendar(year, week, 1).date()
    end_date = start_date + timedelta(days=6)

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

    days = []
    for i in range(7):
        date = start_date + timedelta(days=i)
        day_blocks = [block for block in week_blocks if block.day_of_month == date.day and block.month == date.month]
        days.append({'date': date, 'blocks': day_blocks})

    context = {
        'days': days,
        'week_start': start_date,
        'week_end': end_date,
    }
    return render(request, 'gestao/employee_tasks.html', context)

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect('admin_schedule')
            return redirect('employee_tasks')
        else:
            return render(request, 'gestao/login.html', {'error': 'Invalid credentials'})
    return render(request, 'gestao/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')
