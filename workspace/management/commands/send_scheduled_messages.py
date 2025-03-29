
from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import ScheduledMessage
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends scheduled messages that are due'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # Get all unsent messages that are due
        due_messages = ScheduledMessage.objects.filter(
            is_sent=False,
            scheduled_time__lte=now
        )
        
        if not due_messages.exists():
            self.stdout.write(self.style.SUCCESS('No scheduled messages are due'))
            return
            
        self.stdout.write(f'Found {due_messages.count()} scheduled messages to send')
        
        # Keep track of successes and failures
        success_count = 0
        fail_count = 0
        
        # Process each message
        for scheduled_msg in due_messages:
            try:
                # Send the message
                message = scheduled_msg.send()
                
                if message:
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'Sent scheduled message #{scheduled_msg.id} from {scheduled_msg.sender.username}'
                    ))
                else:
                    fail_count += 1
                    self.stdout.write(self.style.ERROR(
                        f'Failed to send scheduled message #{scheduled_msg.id} (already sent)'
                    ))
            except Exception as e:
                fail_count += 1
                logger.error(f'Error sending scheduled message #{scheduled_msg.id}: {str(e)}')
                self.stdout.write(self.style.ERROR(
                    f'Error sending scheduled message #{scheduled_msg.id}: {str(e)}'
                ))
                
        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'Processed {due_messages.count()} scheduled messages: '
            f'{success_count} sent successfully, {fail_count} failed'
        ))