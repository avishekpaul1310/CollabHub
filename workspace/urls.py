from django.urls import path
from . import views

urlpatterns = [
    # Existing URLs
    path('', views.dashboard, name='dashboard'),
    path('work-item/<int:pk>/', views.work_item_detail, name='work_item_detail'),
    path('work-item/new/', views.create_work_item, name='create_work_item'),
    path('work-item/<int:pk>/update/', views.update_work_item, name='update_work_item'),
    path('work-item/<int:pk>/delete/', views.delete_work_item, name='delete_work_item'),
    path('work-item/<int:pk>/upload-file/', views.upload_file, name='upload_file'),
    
    # Thread management
    path('work-item/<int:work_item_pk>/thread/new/', views.create_thread, name='create_thread'),
    path('work-item/<int:work_item_pk>/thread/<int:thread_pk>/', views.thread_detail, name='thread_detail'),
    path('work-item/<int:work_item_pk>/thread/<int:thread_pk>/update/', views.update_thread, name='update_thread'),
    
    # Notification-related URLs
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),
    
    # Add the missing notification_preferences URL
    path('notifications/preferences/', views.notification_preferences, name='notification_preferences'),
    path('notifications/toggle-mute/<int:pk>/', views.toggle_mute_work_item, name='toggle_mute_work_item'),
]