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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}"
    
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