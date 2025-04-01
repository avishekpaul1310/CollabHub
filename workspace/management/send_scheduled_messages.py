from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import ScheduledMessage, Message

class Command(BaseCommand):
    help = 'Sends scheduled messages whose time has arrived'

    def handle(self, *args, **options):
        now = timezone.now()
        due_messages = ScheduledMessage.objects.filter(
            scheduled_time__lte=now,
            is_sent=False
        )
        
        sent_count = 0
        for scheduled in due_messages:
            # Create actual message
            message = Message.objects.create(
                work_item=scheduled.work_item,
                thread=scheduled.thread,
                user=scheduled.sender,
                content=scheduled.content,
                parent=scheduled.parent_message,
                is_thread_starter=False,
                is_scheduled=True
            )
            
            # Mark as sent
            scheduled.is_sent = True
            scheduled.sent_at = timezone.now()
            scheduled.save()
            sent_count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Successfully sent {sent_count} scheduled messages'))