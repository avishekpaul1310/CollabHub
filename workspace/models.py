from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class WorkItem(models.Model):
    TYPES = [
        ('task', 'Task'),
        ('doc', 'Document'),
        ('project', 'Project')
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPES)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='work_item')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    collaborators = models.ManyToManyField(User, related_name='collaborated_items', blank=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['-updated_at']

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
    
    # Is this notification read?
    is_read = models.BooleanField(default=False)
    
    # When was this notification created
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Notification type (message, update, file_upload)
    notification_type = models.CharField(max_length=20, 
                                        choices=[('message', 'New Message'),
                                                ('update', 'Work Item Update'),
                                                ('file_upload', 'New File')])
    
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
    
    # Channel preferences
    muted_channels = models.ManyToManyField(WorkItem, related_name='muted_by_users', blank=True)
    
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
        
        # Handle case where DND period spans midnight
        if self.dnd_start_time > self.dnd_end_time:
            return now >= self.dnd_start_time or now <= self.dnd_end_time
        else:
            return self.dnd_start_time <= now <= self.dnd_end_time
    
    def should_notify(self, work_item=None):
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
        
        in_work_hours = (
            current_weekday in self.work_days and
            self.work_start_time <= current_time <= self.work_end_time
        )
        
        # If outside work hours and not in a special channel, don't notify
        if not in_work_hours and work_item and not getattr(work_item, 'priority', 'normal') == 'high':
            return False
            
        # Check notification mode
        if self.notification_mode == 'none':
            return False
            
        # Check muted channels
        if work_item and self.muted_channels.filter(id=work_item.id).exists():
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
            
            return message
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error sending scheduled message {self.id}: {str(e)}")
            return False

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


