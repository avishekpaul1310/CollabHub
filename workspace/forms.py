from django import forms
from .models import WorkItem, WorkItemType, Message, FileAttachment, NotificationPreference, Thread, ScheduledMessage, SlowChannel, SlowChannelMessage
from django.contrib.auth.models import User
import datetime
from django.utils import timezone

class WorkItemForm(forms.ModelForm):
    collaborators = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.CheckboxSelectMultiple
    )
    
    class Meta:
        model = WorkItem
        fields = ['title', 'description', 'item_type', 'collaborators']
        widgets = {
            'item_type': forms.Select(attrs={'class': 'form-select'}),
        }
    
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

        # Handle work item types - use custom types and default types
        if self.user:
            # Get all available work item types for the current user
            # This includes types created by the user and some system defaults
            custom_types = WorkItemType.objects.filter(created_by=self.user)
            
            # If no custom types exist, create the default ones
            if not custom_types.exists():
                self._create_default_types()
                custom_types = WorkItemType.objects.filter(created_by=self.user)
            
            # Set the queryset for the item_type field
            self.fields['item_type'].queryset = custom_types
            self.fields['item_type'].empty_label = None
            self.fields['item_type'].label = "Type"
            self.fields['item_type'].help_text = "Select a work item type or <a href='/work-item-types/'>manage your types</a>"
    
    def _create_default_types(self):
        """Create default work item types for a new user"""
        if not self.user:
            return
        
        # Define default types with colors and icons
        defaults = [
            {'name': 'Task', 'color': 'info', 'icon': 'fa-tasks', 
             'description': 'A single actionable item'},
            {'name': 'Document', 'color': 'purple', 'icon': 'fa-file-alt',
             'description': 'Documentation, notes, or written content'},
            {'name': 'Project', 'color': 'warning', 'icon': 'fa-project-diagram',
             'description': 'A collection of related tasks and resources'}
        ]
        
        # Create each default type
        for type_info in defaults:
            WorkItemType.objects.get_or_create(
                name=type_info['name'],
                created_by=self.user,
                defaults={
                    'color': type_info['color'],
                    'icon': type_info['icon'],
                    'description': type_info['description']
                }
            )
    
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

class WorkItemTypeForm(forms.ModelForm):
    """Form for creating and editing work item types"""
    COLOR_CHOICES = [
        ('primary', 'Blue'),
        ('secondary', 'Gray'),
        ('success', 'Green'),
        ('danger', 'Red'),
        ('warning', 'Yellow'),
        ('info', 'Light Blue'),
        ('purple', 'Purple'),
        ('pink', 'Pink'),
        ('orange', 'Orange'),
        ('teal', 'Teal'),
    ]
    
    ICON_CHOICES = [
        ('fa-tasks', 'Tasks'),
        ('fa-file-alt', 'Document'),
        ('fa-project-diagram', 'Project'),
        ('fa-cog', 'Settings'),
        ('fa-bug', 'Bug'),
        ('fa-lightbulb', 'Idea'),
        ('fa-question', 'Question'),
        ('fa-check', 'Checkbox'),
        ('fa-calendar', 'Calendar'),
        ('fa-users', 'Team'),
        ('fa-code', 'Code'),
        ('fa-clipboard', 'Clipboard'),
        ('fa-book', 'Book'),
        ('fa-chart-bar', 'Chart'),
    ]
    
    color = forms.ChoiceField(choices=COLOR_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-select'}))
    icon = forms.ChoiceField(choices=ICON_CHOICES, required=True, widget=forms.Select(attrs={'class': 'form-select'}))
    
    class Meta:
        model = WorkItemType
        fields = ['name', 'description', 'color', 'icon']
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(WorkItemTypeForm, self).__init__(*args, **kwargs)
        
        # Set help texts
        self.fields['name'].help_text = "A short, descriptive name for this type"
        self.fields['description'].help_text = "Optional description of this type"
        self.fields['color'].help_text = "Color used for badges and UI elements"
        self.fields['icon'].help_text = "Icon displayed next to this type"
        
    def save(self, commit=True):
        instance = super(WorkItemTypeForm, self).save(commit=False)
        
        if not instance.pk and self.user:
            instance.created_by = self.user
            
        if commit:
            instance.save()
            
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
        fields = [
            'dnd_enabled', 'dnd_start_time', 'dnd_end_time', 
            'work_days', 'work_start_time', 'work_end_time',
            'notification_mode', 'show_online_status', 'share_read_receipts',
            # Work-life balance fields
            'share_working_hours', 'away_mode', 'away_message', 
            'auto_away_after', 'break_frequency',
            'lunch_break_start', 'lunch_break_duration',
            # Focus mode fields
            'focus_mode', 'focus_users', 'focus_work_items'
        ]
        widgets = {
            'dnd_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'dnd_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'work_end_time': forms.TimeInput(attrs={'type': 'time'}),
            'lunch_break_start': forms.TimeInput(attrs={'type': 'time'}),
            'work_days': forms.CheckboxSelectMultiple(choices=[
                ('1', 'Monday'), ('2', 'Tuesday'), ('3', 'Wednesday'),
                ('4', 'Thursday'), ('5', 'Friday'), ('6', 'Saturday'), ('7', 'Sunday')
            ]),
            'away_message': forms.TextInput(attrs={
                'placeholder': 'Away from keyboard, will respond later...'
            }),
            'auto_away_after': forms.NumberInput(attrs={'min': 5, 'max': 120}),
            'break_frequency': forms.NumberInput(attrs={'min': 15, 'max': 120}),
            'lunch_break_duration': forms.NumberInput(attrs={'min': 15, 'max': 120})
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

class SlowChannelForm(forms.ModelForm):
    delivery_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time'}),
        help_text="When messages will be delivered each day",
        initial=datetime.time(9, 0)  # 9:00 AM default
    )
    
    min_response_interval = forms.IntegerField(
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        label="Minimum response interval (hours)",
        help_text="Minimum time between responses to encourage thoughtfulness",
        initial=4
    )
    
    class Meta:
        model = SlowChannel
        fields = [
            'title', 'description', 'type', 'message_frequency',
            'delivery_time', 'custom_days', 'min_response_interval',
            'reflection_prompts'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'reflection_prompts': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': 'Enter one prompt per line. Example:\nWhat went well this week?\nWhat could be improved?'
            }),
            'custom_days': forms.CheckboxSelectMultiple(choices=[
                ('1', 'Monday'), ('2', 'Tuesday'), ('3', 'Wednesday'),
                ('4', 'Thursday'), ('5', 'Friday'), ('6', 'Saturday'), ('7', 'Sunday')
            ])
        }
    
    def __init__(self, *args, **kwargs):
        self.work_item = kwargs.pop('work_item', None)
        self.user = kwargs.pop('user', None)
        super(SlowChannelForm, self).__init__(*args, **kwargs)
        
        # Set default values if this is a new instance
        if not self.instance.pk:
            self.fields['custom_days'].initial = ['1', '2', '3', '4', '5']  # Monday-Friday by default
        
        # Convert min_response_interval from duration to hours
        instance = kwargs.get('instance')
        if instance and instance.min_response_interval:
            self.initial['min_response_interval'] = instance.min_response_interval.total_seconds() / 3600
    
    def clean_min_response_interval(self):
        """Convert hours to timedelta"""
        hours = self.cleaned_data.get('min_response_interval')
        if isinstance(hours, (int, float)):
            return datetime.timedelta(hours=hours)
        return hours
    
    def clean(self):
        """Validate form data"""
        cleaned_data = super().clean()
        
        # Check if we need to validate custom_days
        message_frequency = cleaned_data.get('message_frequency')
        custom_days = cleaned_data.get('custom_days', [])
        
        if message_frequency in ['custom', 'weekly', 'biweekly'] and not custom_days:
            self.add_error('custom_days', "You must select at least one day for delivery")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super(SlowChannelForm, self).save(commit=False)
        
        # Set the work item if this is a new channel
        if self.work_item and not instance.pk:
            instance.work_item = self.work_item
            
        # Set the creator if this is a new channel
        if self.user and not instance.pk:
            instance.created_by = self.user
            
        if commit:
            instance.save()
            
            # Add creator as participant
            if self.user:
                instance.participants.add(self.user)
                
            # For existing channels with a creator, make sure they're still a participant
            elif hasattr(instance, 'created_by') and instance.created_by:
                instance.participants.add(instance.created_by)
            
        return instance


class SlowChannelMessageForm(forms.ModelForm):
    class Meta:
        model = SlowChannelMessage
        fields = ['content', 'prompt']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Take your time to compose a thoughtful message...'
            }),
            'prompt': forms.HiddenInput()
        }
    
    def __init__(self, *args, **kwargs):
        self.channel = kwargs.pop('channel', None)
        self.user = kwargs.pop('user', None)
        self.parent = kwargs.pop('parent', None)
        super(SlowChannelMessageForm, self).__init__(*args, **kwargs)
        
        # If there are prompts in the channel, add a dropdown field
        if self.channel and self.channel.get_prompts_list():
            prompts = self.channel.get_prompts_list()
            prompt_choices = [('', '-- Select a prompt (optional) --')] + [(p, p) for p in prompts]
            
            self.fields['prompt'] = forms.ChoiceField(
                choices=prompt_choices,
                required=False,
                widget=forms.Select(attrs={'class': 'form-select'})
            )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Check if user can post (min response interval)
        if self.channel and self.user:
            # Get user's last message in this channel
            last_message = SlowChannelMessage.objects.filter(
                channel=self.channel,
                user=self.user
            ).order_by('-created_at').first()
            
            if last_message:
                # Calculate time since last message
                time_since_last = timezone.now() - last_message.created_at
                min_interval = self.channel.min_response_interval
                
                if time_since_last < min_interval and not self.parent:
                    # Only enforce for top-level messages, not replies
                    hours = min_interval.total_seconds() / 3600
                    time_left = min_interval - time_since_last
                    minutes_left = round(time_left.total_seconds() / 60)
                    
                    if minutes_left > 60:
                        time_msg = f"{round(minutes_left/60, 1)} hours"
                    else:
                        time_msg = f"{minutes_left} minutes"
                        
                    raise forms.ValidationError(
                        f"Please wait {time_msg} before posting again. "
                        f"This channel has a minimum interval of {hours} hours between messages "
                        f"to encourage thoughtful communication."
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super(SlowChannelMessageForm, self).save(commit=False)
        
        # Set the channel
        if self.channel:
            instance.channel = self.channel
            
        # Set the user
        if self.user:
            instance.user = self.user
            
        # Set parent for replies
        if self.parent:
            instance.parent = self.parent
        
        # Calculate scheduled delivery time
        if self.channel:
            instance.scheduled_delivery = self.channel.get_next_delivery_time()
        
        if commit:
            instance.save()
            
            # Schedule the message for delivery with Celery
            try:
                from .tasks import schedule_new_message_delivery
                schedule_new_message_delivery.delay(instance.id)
            except ImportError:
                # If Celery isn't available, log a warning
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    "Celery tasks not available. Message delivery scheduling may be delayed."
                )
            
        return instance


class SlowChannelParticipantsForm(forms.Form):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select users who should participate in this slow channel"
    )
    
    def __init__(self, *args, **kwargs):
        self.work_item = kwargs.pop('work_item', None)
        self.channel = kwargs.pop('channel', None)
        super(SlowChannelParticipantsForm, self).__init__(*args, **kwargs)
        
        if self.work_item:
            # Get all collaborators plus the owner
            collaborators = list(self.work_item.collaborators.all())
            
            # Add the owner if they're not already in the list
            if self.work_item.owner not in collaborators:
                collaborators.append(self.work_item.owner)
                
            # Set the queryset
            self.fields['participants'].queryset = User.objects.filter(id__in=[user.id for user in collaborators])
            
            # Set initial value if channel exists
            if self.channel:
                self.fields['participants'].initial = self.channel.participants.all()