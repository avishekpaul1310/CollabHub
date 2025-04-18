from django.contrib.auth.models import User
from .models import Notification
from datetime import datetime
from django.conf import settings

def notifications_processor(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return {'unread_notifications_count': unread_count}
    return {'unread_notifications_count': 0}

def datetime_formats_processor(request):
    """Context processor to add common date/time format strings to template context"""
    return {
        'INDIA_DATE_FORMAT': settings.DATE_FORMAT,
        'INDIA_DATETIME_FORMAT': settings.DATETIME_FORMAT,
        'INDIA_SHORT_DATE_FORMAT': settings.SHORT_DATE_FORMAT,
        'INDIA_SHORT_DATETIME_FORMAT': settings.SHORT_DATETIME_FORMAT,
        'INDIA_TIME_FORMAT': settings.TIME_FORMAT,
        'CURRENT_DATETIME': datetime.now(),
    }