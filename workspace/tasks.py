from celery import shared_task
from django.utils import timezone
from .models import ScheduledMessage, Message

@shared_task
def send_scheduled_messages():
    now = timezone.now()
    messages = ScheduledMessage.objects.filter(is_sent=False, scheduled_time__lte=now)
    
    for message in messages:
        # Create actual message from scheduled one
        actual_message = Message(
            work_item=message.work_item,
            thread=message.thread,
            user=message.sender,
            content=message.content,
            parent=message.parent_message,
            is_scheduled=True
        )
        actual_message.save()
        
        # Mark scheduled message as sent
        message.is_sent = True
        message.sent_at = timezone.now()
        message.save()  # Added this line to actually save the changes