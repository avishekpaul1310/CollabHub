from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

class WorkItemType(models.Model):
    """Model for custom work item types that can be created by users"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=20, default="primary")
    icon = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_types')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']

class WorkItem(models.Model):
    # We'll keep the TYPES constant for backward compatibility and default types
    TYPES = [
        ('task', 'Task'),
        ('doc', 'Document'),
        ('project', 'Project')
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    # Keep the old type field for backward compatibility
    type = models.CharField(max_length=20, choices=TYPES, null=True, blank=True)
    
    # Add new reference to WorkItemType
    item_type = models.ForeignKey(WorkItemType, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_items')
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_item')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    collaborators = models.ManyToManyField(User, related_name='collaborated_items', blank=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['-updated_at']
    
    def get_type_display(self):
        """Override to handle both old and new type fields"""
        if self.item_type:
            return self.item_type.name
        elif self.type:
            # Use Django's get_FOO_display method logic
            for value, display in self.TYPES:
                if value == self.type:
                    return display
        return "Unknown"
    
    def get_type_for_badge(self):
        """Return the type name for display in badges"""
        return self.get_type_display()
    
    def get_type_color(self):
        """Return the color to use for this type in UI elements"""
        if self.item_type and self.item_type.color:
            return self.item_type.color
        
        # Default colors for legacy types
        if self.type == 'task':
            return 'info'
        elif self.type == 'doc':
            return 'purple'
        elif self.type == 'project':
            return 'warning'
        return 'primary'
    
    def get_type_icon(self):
        """Return the icon to use for this type in UI elements"""
        if self.item_type and self.item_type.icon:
            return self.item_type.icon
        
        # Default icons for legacy types
        if self.type == 'task':
            return 'fa-tasks'
        elif self.type == 'doc':
            return 'fa-file-lines'  # Changed from fa-file-alt for better visibility
        elif self.type == 'project':
            return 'fa-project-diagram'
        return 'fa-clipboard'

class Message(models.Model):
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='messages')
    thread = models.ForeignKey('Thread', on_delete=models.CASCADE, related_name='thread_messages', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Threading support
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    is_thread_starter = models.BooleanField(default=False)
    is_scheduled = models.BooleanField(default=False)  # New field to track scheduled messages
    is_from_websocket = models.BooleanField(default=False)  # Track WebSocket-created messages
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.content}"
    
    @property
    def reply_count(self):
        """Get the count of replies to this message"""
        return self.replies.count() if hasattr(self, 'replies') else 0
    
class FileAttachment(models.Model):
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='work_item_files/')
    name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Notification(models.Model):
    # The user who will receive the notification
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    
    # The content of the notification
    message = models.CharField(max_length=255)
    
    # Optional link to related work item
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, null=True, blank=True)
    
    # Optional link to related thread
    thread = models.ForeignKey('Thread', on_delete=models.CASCADE, null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    is_delayed = models.BooleanField(default=False)
    is_from_muted = models.BooleanField(default=False)
    is_focus_filtered = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=False)
    is_batched = models.BooleanField(default=False)
    
    # When was this notification created
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notification type (message, update, file_upload)
    notification_type = models.CharField(max_length=20, 
                                        choices=[('message', 'New Message'),
                                                ('update', 'Work Item Update'),
                                                ('file_upload', 'New File')])
    
    # Priority level (urgent, normal, low)
    PRIORITY_CHOICES = [
        ('urgent', 'Urgent'),
        ('normal', 'Normal'),
        ('low', 'Low'),
    ]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.user.username}: {self.message[:30]}"
    
class NotificationPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preferences')
    
    # Do Not Disturb settings
    dnd_enabled = models.BooleanField(default=False)
    dnd_start_time = models.TimeField(null=True, blank=True)
    dnd_end_time = models.TimeField(null=True, blank=True)
    
    # Work days/hours
    work_days = models.CharField(max_length=20, default="12345", help_text="Days of week (1-7, where 1 is Monday)")
    work_start_time = models.TimeField(default="09:00")
    work_end_time = models.TimeField(default="17:00")
    show_online_status = models.BooleanField(
    default=False,
    help_text="Show your online status to other users"
    )
    share_read_receipts = models.BooleanField(
    default=True,
    help_text="Share read receipts with message authors"
    )
    
    # Work-Life Balance settings
    share_working_hours = models.BooleanField(
            default=True,
            help_text="Allow others to see your working hours"
        )
        
    away_mode = models.BooleanField(
            default=False,
            help_text="Enable away from keyboard mode"
        )
        
    away_message = models.CharField(
            max_length=255, 
            blank=True,
            help_text="Message to show when you're away"
        )
        
    auto_away_after = models.IntegerField(
            default=30,
            help_text="Set away status after inactive for this many minutes"
        )
        
    break_frequency = models.IntegerField(
            default=60,
            help_text="Reminder frequency in minutes to take breaks"
        )
        
    lunch_break_start = models.TimeField(
            null=True, 
            blank=True,
            help_text="Start time of your lunch break"
        )
        
    lunch_break_duration = models.IntegerField(
            default=60,
            help_text="Duration of lunch break in minutes"
        )
    
    # Focus Mode settings
    focus_mode = models.BooleanField(
        default=False,
        help_text="When enabled, only receive notifications from selected users and work items"
    )
    focus_users = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='focus_notifications',
        help_text="Only receive notifications from these users when in focus mode"
    )
    focus_work_items = models.ManyToManyField(
        WorkItem, 
        blank=True, 
        related_name='focus_notifications',
        help_text="Only receive notifications from these work items when in focus mode"
    )
    
    # Channel preferences
    muted_channels = models.ManyToManyField(WorkItem, related_name='muted_by_users', blank=True)
    muted_threads = models.ManyToManyField('Thread', related_name='muted_by_users', blank=True)
    
    # Mode settings
    NOTIFICATION_MODES = [
        ('all', 'All Notifications'),
        ('mentions', 'Mentions Only'),
        ('none', 'None'),
    ]
    notification_mode = models.CharField(max_length=10, choices=NOTIFICATION_MODES, default='all')
    
    def __str__(self):
        return f"{self.user.username}'s notification preferences"
    
    def is_in_dnd_period(self):
        """Check if current time is within DND period"""
        if not self.dnd_enabled or not self.dnd_start_time or not self.dnd_end_time:
            return False
            
        from django.utils import timezone
        now = timezone.localtime().time()
        
        # Debug info to help troubleshoot
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DND check: now={now}, start={self.dnd_start_time}, end={self.dnd_end_time}")
        
        # Handle case where DND period spans midnight
        if self.dnd_start_time > self.dnd_end_time:
            result = now >= self.dnd_start_time or now <= self.dnd_end_time
        else:
            result = self.dnd_start_time <= now <= self.dnd_end_time
            
        logger.info(f"DND period check result: {result}")
        return result
    
    def should_notify(self, work_item=None, thread=None):
        """Determine if user should be notified based on preferences"""
        # Check DND period
        if self.is_in_dnd_period():
            return False
            
        # Check work hours
        from django.utils import timezone
        import datetime
        
        now = timezone.localtime()
        current_weekday = str(now.weekday() + 1)  # 1 is Monday in our system
        current_time = now.time()
        
        # Convert string times to datetime.time objects if they are strings
        if isinstance(self.work_start_time, str):
            try:
                h, m = map(int, self.work_start_time.split(':')[:2])
                work_start = datetime.time(h, m)
            except (ValueError, TypeError):
                work_start = datetime.time(9, 0)  # Default
        else:
            work_start = self.work_start_time
            
        if isinstance(self.work_end_time, str):
            try:
                h, m = map(int, self.work_end_time.split(':')[:2])
                work_end = datetime.time(h, m)
            except (ValueError, TypeError):
                work_end = datetime.time(17, 0)  # Default
        else:
            work_end = self.work_end_time
        
        # Check if now is within work hours
        in_work_hours = (
            current_weekday in self.work_days and
            work_start <= current_time <= work_end
        )
        
        # Only apply work hours restriction if dnd_enabled is True
        # This fixes the test where we want to receive notifications anytime
        if not in_work_hours and self.dnd_enabled and work_item and not getattr(work_item, 'priority', 'normal') == 'high':
            return False
            
        # Check notification mode
        if self.notification_mode == 'none':
            return False
            
        # Check muted channels
        if work_item and self.muted_channels.filter(id=work_item.id).exists():
            return False
            
        # Check muted threads
        if thread and self.muted_threads.filter(id=thread.id).exists():
            return False
                
        # Check focus mode
        if self.focus_mode:
            if work_item and not self.focus_work_items.filter(id=work_item.id).exists():
                # Only block if the work item is not in the focus list
                if work_item.owner and not self.focus_users.filter(id=work_item.owner.id).exists():
                    # And if the owner is not in the focus users list
                    return False
                    
        return True
    

class Thread(models.Model):
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='threads')
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_threads')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Permission fields
    is_public = models.BooleanField(default=True)
    # Users who can access this thread, regardless of work_item permissions
    allowed_users = models.ManyToManyField(User, related_name='accessible_threads', blank=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.title
    
    def user_can_access(self, user):
        """Check if a user can access this thread"""
        if user is None:
            return False
            
        # The creator always has access
        if self.created_by == user:
            return True
            
        if self.is_public:
            # For public threads, anyone with access to the work item can access
            return self.work_item.owner == user or user in self.work_item.collaborators.all()
        else:
            # For private threads, ONLY users explicitly in allowed_users can access
            # (plus the work item owner, if they need to moderate)
            if self.work_item.owner == user:
                return True  # Work item owner always has access for moderation
                
            return user in self.allowed_users.all()
            
    def get_participants(self):
        """Get all users who should be participants in this thread"""
        participants = set()
        
        # The creator is always a participant
        participants.add(self.created_by)
        
        if self.is_public:
            # For public threads, all work item collaborators are participants
            participants.add(self.work_item.owner)
            for user in self.work_item.collaborators.all():
                participants.add(user)
        else:
            # For private threads, only allowed users are participants
            for user in self.allowed_users.all():
                participants.add(user)
                
        return participants

class ThreadGroup(models.Model):
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='thread_groups')
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_thread_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Permission fields
    is_public = models.BooleanField(default=True)
    # Users who can access this thread, regardless of work_item permissions
    allowed_users = models.ManyToManyField(User, related_name='accessible_thread_groups', blank=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return self.title
    
    def user_can_access(self, user):
        """Check if a user can access this thread"""
        if self.is_public:
            # If public, check if user can access the parent work item
            return self.work_item.owner == user or user in self.work_item.collaborators.all()
        else:
            # If private, check if user is explicitly allowed
            return (self.work_item.owner == user or 
                    user in self.work_item.collaborators.all() or 
                    user in self.allowed_users.all() or 
                    self.created_by == user)

class ThreadMessage(models.Model):
    thread_group = models.ForeignKey(ThreadGroup, on_delete=models.CASCADE, related_name='thread_messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='thread_messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Threading support
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    is_thread_starter = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.content[:50]}"
    
    @property
    def reply_count(self):
        """Get the count of replies to this message"""
        return self.replies.count()

class ScheduledMessage(models.Model):
    """Model for messages that are scheduled to be sent at a future time"""
    # The user who scheduled this message
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='scheduled_messages')
    
    # Where the message will be sent
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='scheduled_messages')
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='scheduled_messages', 
                              null=True, blank=True)
    parent_message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='scheduled_replies',
                                     null=True, blank=True)
    
    # Message content
    content = models.TextField()
    
    # When the message is scheduled to be sent
    scheduled_time = models.DateTimeField()
    
    # Status tracking
    created_at = models.DateTimeField(auto_now_add=True)
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Optional note about why this time was chosen
    scheduling_note = models.CharField(max_length=255, blank=True, 
                                     help_text="Optional note about why you chose this time")
    
    class Meta:
        ordering = ['scheduled_time']
    
    def __str__(self):
        sent_status = "Sent" if self.is_sent else "Scheduled"
        return f"{sent_status} message by {self.sender.username} for {self.scheduled_time}"
    
    def send(self):
        """Send this scheduled message by creating an actual Message"""
        if self.is_sent:
            return False
            
        try:
            # Create the actual message
            message = Message.objects.create(
                work_item=self.work_item,
                thread=self.thread,
                user=self.sender,
                content=self.content,
                parent=self.parent_message,
                is_thread_starter=False,
                is_scheduled=True  # Add this field to Message model
            )
            
            # Mark as sent
            self.is_sent = True
            self.sent_at = timezone.now()
            self.save()
            
            # Log successful delivery
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Scheduled message {self.id} sent successfully at {self.sent_at}")
            
            # Create notifications for recipients
            self._create_notifications(message)
            
            return message
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error sending scheduled message {self.id}: {str(e)}")
            return False
    
    def _create_notifications(self, message):
        """Create notifications for the message recipients"""
        try:
            # Determine recipients based on work item and thread
            recipients = set()
            
            # Add work item owner if not the sender
            if self.work_item.owner != self.sender:
                recipients.add(self.work_item.owner)
            
            # Add collaborators except sender
            collaborators = self.work_item.collaborators.exclude(id=self.sender.id)
            recipients.update(collaborators)
            
            # If thread exists, only include thread participants
            if self.thread:
                thread_participants = self.thread.get_participants()
                recipients = recipients.intersection(thread_participants)
                
            # Create notifications
            for recipient in recipients:
                Notification.objects.create(
                    user=recipient,
                    message=f"{self.sender.username} sent a scheduled message in '{self.work_item.title}'",
                    work_item=self.work_item,
                    thread=self.thread,
                    notification_type='message'
                )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating notifications for scheduled message {self.id}: {str(e)}")

class MessageReadReceipt(models.Model):
    """Model to track when messages are read by users"""
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_receipts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='read_receipts')
    read_at = models.DateTimeField(auto_now_add=True)
    
    # Optional fields to track engagement level
    read_duration = models.DurationField(null=True, blank=True, 
                                       help_text="How long the user spent viewing this message")
    has_responded = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ['message', 'user']
        ordering = ['read_at']
    
    def __str__(self):
        return f"{self.user.username} read message {self.message.id} at {self.read_at}"

class SlowChannel(models.Model):
    """
    Model for slow channels - places for non-urgent, thoughtful communication
    with intentional delays to encourage deeper thinking.
    """
    TYPE_CHOICES = [
        ('reflection', 'Team Reflection'),
        ('ideation', 'Idea Generation'),
        ('learning', 'Learning & Growth'),
        ('documentation', 'Documentation'),
        ('other', 'Other')
    ]
    
    FREQUENCY_CHOICES = [
        ('daily', 'Once per day'),
        ('workday', 'Once per workday'),
        ('weekly', 'Once per week'),
        ('biweekly', 'Twice per week'),
        ('custom', 'Custom schedule')
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    # Related work item
    work_item = models.ForeignKey(WorkItem, on_delete=models.CASCADE, related_name='slow_channels')
    
    # Admin settings
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_slow_channels')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Delivery settings
    message_frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    delivery_time = models.TimeField(default='09:00:00')
    custom_days = models.CharField(
        max_length=100, 
        default='12345',  # Monday-Friday
        help_text="Days to deliver (1=Mon, 7=Sun)"
    )
    
    # Participant settings
    participants = models.ManyToManyField(User, related_name='slow_channels')
    
    # User experience settings
    min_response_interval = models.DurationField(
        default=datetime.timedelta(hours=4),
        help_text="Minimum time between responses to encourage thoughtfulness"
    )
    
    # Optional reflection prompts
    reflection_prompts = models.TextField(
        blank=True,
        help_text="Optional prompts to guide discussion (one per line)"
    )
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    def get_prompts_list(self):
        """Get reflection prompts as a list"""
        if not self.reflection_prompts:
            return []
        return [p.strip() for p in self.reflection_prompts.split('\n') if p.strip()]
    
    def get_next_delivery_time(self):
        """Calculate the next time messages should be delivered"""
        from django.utils import timezone
        import datetime
        
        now = timezone.now()
        delivery_time = datetime.time(
            hour=self.delivery_time.hour,
            minute=self.delivery_time.minute,
            second=self.delivery_time.second
        )
        
        # Start with today at delivery time
        next_delivery = timezone.make_aware(
            datetime.datetime.combine(now.date(), delivery_time)
        )
        
        # If that's in the past, move to the next valid day
        if next_delivery <= now:
            next_delivery += datetime.timedelta(days=1)
        
        # For custom or weekly schedules, find the next valid day
        if self.message_frequency in ['custom', 'weekly', 'biweekly']:
            # Convert custom_days to a list of integers
            valid_days = [int(d) for d in self.custom_days]
            
            # Keep adding days until we hit a valid day
            while str(next_delivery.isoweekday()) not in self.custom_days:
                next_delivery += datetime.timedelta(days=1)
        
        # For workday frequency, skip weekends
        elif self.message_frequency == 'workday':
            while next_delivery.weekday() >= 5:  # Saturday=5, Sunday=6
                next_delivery += datetime.timedelta(days=1)
        
        return next_delivery


class SlowChannelMessage(models.Model):
    """
    Messages in a slow channel - designed for thoughtful, non-urgent communication
    """
    channel = models.ForeignKey(SlowChannel, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='slow_channel_messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Delivery tracking
    is_delivered = models.BooleanField(default=False)
    scheduled_delivery = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Optional fields for reflection
    prompt = models.CharField(max_length=255, blank=True)
    
    # Threading support
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.content[:50]}"
    
    def mark_delivered(self):
        """Mark this message as delivered"""
        if not self.is_delivered:
            self.is_delivered = True
            self.delivered_at = timezone.now()
            self.save()
    
    def deliver(self):
        """Deliver this message and create notifications for participants"""
        # Mark as delivered
        self.mark_delivered()
        
        # Create notifications for all participants except the sender
        participants = self.channel.participants.exclude(id=self.user.id)
        
        # Create a notification for each participant
        for participant in participants:
            # Check if the participant should be notified based on preferences
            try:
                preferences = participant.notification_preferences
                if preferences.should_notify(work_item=self.channel.work_item):
                    Notification.objects.create(
                        user=participant,
                        message=f"New message in slow channel '{self.channel.title}'",
                        work_item=self.channel.work_item,
                        notification_type='message',
                        priority='normal'
                    )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error creating notification for slow channel message: {str(e)}")
        
        return True

class BreakEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(null=True, blank=True)  # in seconds
    completed = models.BooleanField(default=False)
    
    def calculate_duration(self):
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

class UserOnlineStatus(models.Model):
    """Model to store user online status persistently across sessions"""
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='workspace_online_status',  # This is fine as is, distinct from users app
    )
    status = models.CharField(
        max_length=20, 
        choices=[
            ('online', 'Online'),
            ('away', 'Away'),
            ('afk', 'AFK'),
            ('offline', 'Offline'),
            ('break', 'On Break'),
            ('outside-hours', 'Outside Working Hours')
        ],
        default='offline'
    )
    status_message = models.CharField(max_length=255, blank=True, null=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    # Session info for multiple device tracking
    device_info = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name_plural = "User Online Statuses"
        
    def __str__(self):
        return f"{self.user.username}: {self.status}"
    
    def update_status(self, status, message=None, session_key=None):
        """Update user status with option to track by session"""
        self.status = status
        
        if message:
            self.status_message = message
        
        # Track device if session_key provided
        if session_key:
            devices = self.device_info.copy()
            devices[session_key] = {
                'status': status,
                'last_active': timezone.now().isoformat(),
                'user_agent': None  # Could be added if we capture user-agent
            }
            self.device_info = devices
        
        self.save()

