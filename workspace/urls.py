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
    path('work-item/<int:pk>/remove-collaborator/<int:user_id>/', views.remove_collaborator, name='remove_collaborator'),
    
    # Work Item Types management
    path('work-item-types/', views.work_item_types_list, name='work_item_types_list'),
    path('work-item-types/new/', views.create_work_item_type, name='create_work_item_type'),
    path('work-item-types/<int:pk>/update/', views.update_work_item_type, name='update_work_item_type'),
    path('work-item-types/<int:pk>/delete/', views.delete_work_item_type, name='delete_work_item_type'),
    
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
    path('notifications/toggle-mute-thread/<int:pk>/', views.toggle_mute_thread, name='toggle_mute_thread'),

    # Scheduled Message URLs
    path('work-item/<int:work_item_pk>/schedule-message/', views.schedule_message, name='schedule_message'),
    path('work-item/<int:work_item_pk>/thread/<int:thread_pk>/schedule-message/', views.schedule_message, name='schedule_thread_message'),
    path('work-item/<int:work_item_pk>/thread/<int:thread_pk>/message/<int:parent_message_pk>/schedule-reply/', views.schedule_message, name='schedule_reply'),
    path('my-scheduled-messages/', views.my_scheduled_messages, name='my_scheduled_messages'),
    path('scheduled-message/<int:pk>/cancel/', views.cancel_scheduled_message, name='cancel_scheduled_message'),
    path('scheduled-message/<int:pk>/edit/', views.edit_scheduled_message, name='edit_scheduled_message'),
    path('run-scheduled-messages/', views.manually_run_scheduled_messages, name='run_scheduled_messages'),

    # Read Receipts URLs
    path('api/message/<int:message_id>/mark-read/', views.mark_message_read, name='mark_message_read'),
    path('api/message/<int:message_id>/read-status/', views.get_message_read_status, name='get_message_read_status'),
    path('api/thread/<int:thread_id>/mark-read/', views.mark_thread_read, name='mark_thread_read'),

    # Slow Channel URLs
    path('work-item/<int:work_item_pk>/slow-channel/new/', views.create_slow_channel, name='create_slow_channel'),
    path('slow-channel/<int:channel_pk>/', views.slow_channel_detail, name='slow_channel_detail'),
    path('slow-channel/<int:channel_pk>/update/', views.update_slow_channel, name='update_slow_channel'),
    path('slow-channel/<int:channel_pk>/delete/', views.delete_slow_channel, name='delete_slow_channel'),
    path('slow-channel/<int:channel_pk>/join/', views.join_slow_channel, name='join_slow_channel'),
    path('slow-channel/<int:channel_pk>/leave/', views.leave_slow_channel, name='leave_slow_channel'),
    path('my-slow-channels/', views.my_slow_channels, name='my_slow_channels'),

# Online Status URLs
    path('api/user/preferences/online-status/', views.get_online_status_preference, name='get_online_status_preference'),
    path('api/user/online-status/', views.update_online_status, name='update_online_status'),
    path('api/user/<int:user_id>/online-status/', views.get_user_online_status, name='get_user_online_status'),

    # Work-Life Balance URLs
    path('api/user/work_life_balance_preferences/', views.get_work_life_balance_preferences, name='work_life_balance_preferences'),
    path('api/user/<int:user_id>/status/', views.get_user_status, name='get_user_status'),
    path('api/work_session/log/', views.log_work_session, name='log_work_session'),
    path('api/work_analytics/', views.get_work_analytics, name='get_work_analytics'),
    path('work-life-analytics/', views.work_life_analytics, name='work_life_analytics'),
    path('api/record-break/', views.record_break_taken, name='record_break_taken'),
]