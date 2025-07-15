from django.urls import path
from . import views

urlpatterns = [
    path('admin-schedule/', views.index, name='admin_schedule'),
    path('admin-schedule/<int:year>/<int:week>/', views.index, name='admin_schedule_week'),
    path('employee-tasks/', views.employee_tasks, name='employee_tasks'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
