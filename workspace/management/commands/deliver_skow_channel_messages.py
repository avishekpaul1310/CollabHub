# workspace/management/commands/deliver_slow_channel_messages.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import SlowChannelMessage
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Delivers scheduled slow channel messages that are due'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Get all undelivered messages that are due
        due_messages = SlowChannelMessage.objects.filter(
            is_delivered=False,
            scheduled_delivery__lte=now
        )
        
        if not due_messages.exists():
            self.stdout.write(self.style.SUCCESS('No slow channel messages are due for delivery'))
            return
            
        self.stdout.write(f'Found {due_messages.count()} slow channel messages to deliver')
        
        # Keep track of successes and failures
        success_count = 0
        fail_count = 0
        
        # Process each message
        for message in due_messages:
            try:
                message.mark_delivered()
                success_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Delivered slow channel message #{message.id} from {message.user.username} '
                    f'in channel "{message.channel.title}"'
                ))
            except Exception as e:
                fail_count += 1
                logger.error(f'Error delivering slow channel message #{message.id}: {str(e)}')
                self.stdout.write(self.style.ERROR(
                    f'Error delivering slow channel message #{message.id}: {str(e)}'
                ))
                
        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'Processed {due_messages.count()} slow channel messages: '
            f'{success_count} delivered successfully, {fail_count} failed'
        ))