from celery import shared_task
from django.utils import timezone
from .models import ScheduledMessage, Message, SlowChannelMessage
import logging

logger = logging.getLogger(__name__)

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
        message.save()

@shared_task
def deliver_slow_channel_messages():
    """Task to deliver scheduled slow channel messages"""
    now = timezone.now()
    
    # Get all undelivered messages that are due
    due_messages = SlowChannelMessage.objects.filter(
        is_delivered=False,
        scheduled_delivery__lte=now
    )
    
    if not due_messages.exists():
        logger.info('No slow channel messages are due for delivery')
        return {'status': 'success', 'delivered': 0, 'failed': 0}
        
    logger.info(f'Found {due_messages.count()} slow channel messages to deliver')
    
    # Keep track of successes and failures
    success_count = 0
    fail_count = 0
    
    # Process each message
    for message in due_messages:
        try:
            message.deliver()
            success_count += 1
            logger.info(
                f'Delivered slow channel message #{message.id} from {message.user.username} '
                f'in channel "{message.channel.title}"'
            )
        except Exception as e:
            fail_count += 1
            logger.error(f'Error delivering slow channel message #{message.id}: {str(e)}')
            
    # Summary
    logger.info(
        f'Processed {due_messages.count()} slow channel messages: '
        f'{success_count} delivered successfully, {fail_count} failed'
    )
    
    return {
        'status': 'success',
        'delivered': success_count,
        'failed': fail_count
    }

@shared_task
def schedule_new_message_delivery(message_id):
    """Schedule delivery for a newly created message"""
    try:
        message = SlowChannelMessage.objects.get(id=message_id)
        
        # If no scheduled delivery time was set, set one now
        if not message.scheduled_delivery:
            message.scheduled_delivery = message.channel.get_next_delivery_time()
            message.save()
            
        logger.info(f'Scheduled message #{message_id} for delivery at {message.scheduled_delivery}')
        return {'status': 'success', 'scheduled_time': message.scheduled_delivery.isoformat()}
    
    except SlowChannelMessage.DoesNotExist:
        logger.error(f'Message #{message_id} not found')
        return {'status': 'error', 'message': f'Message #{message_id} not found'}
    except Exception as e:
        logger.error(f'Error scheduling message #{message_id}: {str(e)}')
        return {'status': 'error', 'message': str(e)}