from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('work-item/<int:pk>/', views.work_item_detail, name='work_item_detail'),
    path('work-item/new/', views.create_work_item, name='create_work_item'),
    path('work-item/<int:pk>/update/', views.update_work_item, name='update_work_item'),
    path('work-item/<int:pk>/delete/', views.delete_work_item, name='delete_work_item'),
    path('work-item/<int:pk>/upload-file/', views.upload_file, name='upload_file'),
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),
]