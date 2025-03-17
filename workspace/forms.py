from django import forms
from .models import WorkItem, Message, FileAttachment
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