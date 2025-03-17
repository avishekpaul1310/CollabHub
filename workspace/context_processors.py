# Create a new file called context_processors.py in your workspace app

def notifications_processor(request):
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': request.user.notifications.filter(is_read=False).count()
        }
    return {'unread_notifications_count': 0}