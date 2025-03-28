from django import forms
from .models import WorkItem, Message, FileAttachment, NotificationPreference, Thread
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
        
        # Limit allowed users to collaborators of the work item
        if self.work_item:
            collaborators = self.work_item.collaborators.all()
            self.fields['allowed_users'].queryset = collaborators
            self.fields['allowed_users'].label = "Select users who can access this thread"
            
    def save(self, commit=True):
        instance = super(ThreadForm, self).save(commit=False)
        
        if self.work_item and not instance.pk:
            instance.work_item = self.work_item
            
        if self.user and not instance.pk:
            instance.created_by = self.user
            
        if commit:
            instance.save()
            self.save_m2m()
            
        return instance