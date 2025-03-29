from django import forms
from .models import WorkItem, Message, FileAttachment, NotificationPreference, Thread, ScheduledMessage
from django.contrib.auth.models import User

class WorkItemForm(forms.ModelForm):
    collaborators = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    
    class Meta:
        model = WorkItem
        fields = ['title', 'description', 'type', 'collaborators']
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(WorkItemForm, self).__init__(*args, **kwargs)
        
        # Initialize the queryset for collaborators
        
        if 'collaborators' in self.fields:
            # Get all users except the current user
            if self.user:
                self.fields['collaborators'].queryset = User.objects.exclude(id=self.user.id)
            else:
                self.fields['collaborators'].queryset = User.objects.all()
        
        # Make collaborators field not required
        self.fields['collaborators'].required = False
    
    def save(self, commit=True):
        instance = super(WorkItemForm, self).save(commit=False)
        
        # Set the owner if this is a new instance
        if not instance.pk and self.user:
            instance.owner = self.user
            
        if commit:
            instance.save()
            # Now it's safe to save many-to-many relationships
            self.save_m2m()
            
        return instance

class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']

class FileAttachmentForm(forms.ModelForm):
    class Meta:
        model = FileAttachment
        fields = ['file']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].label = ''

class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = ['dnd_enabled', 'dnd_start_time', 'dnd_end_time', 
                  'work_days', 'work_start_time', 'work_end_time',
                  'notification_mode']
        widgets = {
            'dnd_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'dnd_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_days': forms.CheckboxSelectMultiple(choices=[
                ('1', 'Monday'), ('2', 'Tuesday'), ('3', 'Wednesday'),
                ('4', 'Thursday'), ('5', 'Friday'), ('6', 'Saturday'), ('7', 'Sunday')
            ])
        }

class ThreadForm(forms.ModelForm):
    class Meta:
        model = Thread
        fields = ['title', 'is_public', 'allowed_users']
        
    def __init__(self, *args, **kwargs):
        self.work_item = kwargs.pop('work_item', None)
        self.user = kwargs.pop('user', None)
        super(ThreadForm, self).__init__(*args, **kwargs)
        
        # Limit allowed users to collaborators of the work item plus the owner
        if self.work_item:
            # Get all collaborators plus the owner
            collaborators = list(self.work_item.collaborators.all())
            
            # Add the owner if they're not already in the list
            if self.work_item.owner not in collaborators:
                collaborators.append(self.work_item.owner)
                
            # Remove current user from the list (they're automatically included)
            if self.user in collaborators:
                collaborators.remove(self.user)
                
            # Set the queryset
            self.fields['allowed_users'].queryset = User.objects.filter(id__in=[user.id for user in collaborators])
            self.fields['allowed_users'].help_text = "Select users who will have access to this private thread"
            
    def clean(self):
        cleaned_data = super().clean()
        is_public = cleaned_data.get('is_public')
        allowed_users = cleaned_data.get('allowed_users')
        
        # If thread is private but no users are selected, show an error
        if not is_public and not allowed_users:
            self.add_error('allowed_users', 'For a private thread, you must select at least one user to share with.')
            
        return cleaned_data
            
    def save(self, commit=True):
        instance = super(ThreadForm, self).save(commit=False)
        
        # Set the work item if this is a new thread
        if self.work_item and not instance.pk:
            instance.work_item = self.work_item
            
        # Set the creator if this is a new thread
        if self.user and not instance.pk:
            instance.created_by = self.user
            
        if commit:
            instance.save()
            
            # Save many-to-many relationships
            self.save_m2m()
            
            # For private threads, make sure the creator has access
            if not instance.is_public and self.user:
                # This step is important - the creator might not be in allowed_users
                instance.allowed_users.add(self.user)
            
        return instance

class ScheduledMessageForm(forms.ModelForm):
    scheduled_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        help_text="When this message should be sent"
    )
    
    class Meta:
        model = ScheduledMessage
        fields = ['content', 'scheduled_time', 'scheduling_note']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Your message content'}),
            'scheduling_note': forms.TextInput(attrs={'placeholder': 'Optional: Why are you scheduling this message?'})
        }
    
    def __init__(self, *args, **kwargs):
        self.sender = kwargs.pop('sender', None)
        self.work_item = kwargs.pop('work_item', None)
        self.thread = kwargs.pop('thread', None)
        self.parent_message = kwargs.pop('parent_message', None)
        
        super(ScheduledMessageForm, self).__init__(*args, **kwargs)
        
        # Set min date to current time
        import datetime
        now = datetime.datetime.now()
        self.fields['scheduled_time'].widget.attrs['min'] = now.strftime('%Y-%m-%dT%H:%M')
    
    def clean_scheduled_time(self):
        """Ensure scheduled time is in the future"""
        scheduled_time = self.cleaned_data.get('scheduled_time')
        from django.utils import timezone
        now = timezone.now()
        
        if scheduled_time and scheduled_time <= now:
            raise forms.ValidationError("Scheduled time must be in the future")
        
        return scheduled_time
    
    def save(self, commit=True):
        instance = super(ScheduledMessageForm, self).save(commit=False)
        
        # Set the sender
        if self.sender:
            instance.sender = self.sender
            
        # Set the work item
        if self.work_item:
            instance.work_item = self.work_item
        
        # Set thread if provided
        if self.thread:
            instance.thread = self.thread
            
        # Set parent message if provided
        if self.parent_message:
            instance.parent_message = self.parent_message
        
        if commit:
            instance.save()
            
        return instance