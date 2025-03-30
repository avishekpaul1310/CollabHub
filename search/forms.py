from django import forms
from django.contrib.auth.models import User
from workspace.models import WorkItem
from .models import SavedSearch

class AdvancedSearchForm(forms.Form):
    """Form for advanced search with filters"""
    # Content type filters
    content_types = forms.MultipleChoiceField(
        choices=[
            ('work_item', 'Work Items'),
            ('message', 'Messages'),
            ('thread', 'Threads'),
            ('file', 'Files'),
            ('channel', 'Slow Channels')
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )
    
    # Work item type filter
    type = forms.ChoiceField(
        choices=[('', 'All Types')] + WorkItem.TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # User filters
    user = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Filter by username'})
    )
    
    owner = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Filter by owner'})
    )
    
    # Date range filters
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    
    # Recent content shortcut
    recent = forms.ChoiceField(
        choices=[
            ('', 'Any time'),
            ('1', 'Last 24 hours'),
            ('7', 'Last week'),
            ('30', 'Last month'),
            ('90', 'Last 3 months')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Thread specific filters
    thread = forms.ChoiceField(
        choices=[
            ('', 'All messages'),
            ('only', 'Only in threads'),
            ('exclude', 'Exclude threads')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Thread visibility
    visibility = forms.ChoiceField(
        choices=[
            ('', 'All threads'),
            ('public', 'Public only'),
            ('private', 'Private only')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # File type filter
    file_type = forms.ChoiceField(
        choices=[
            ('', 'All files'),
            ('document', 'Documents'),
            ('image', 'Images'),
            ('spreadsheet', 'Spreadsheets'),
            ('code', 'Code files')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # Slow channel type filter
    channel_type = forms.ChoiceField(
        choices=[
            ('', 'All channels'),
            ('reflection', 'Team Reflection'),
            ('ideation', 'Idea Generation'),
            ('learning', 'Learning & Growth'), 
            ('documentation', 'Documentation'),
            ('other', 'Other')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make all fields optional and apply Bootstrap styles
        for field_name, field in self.fields.items():
            field.required = False
            if not hasattr(field.widget, 'attrs') or field.widget.attrs is None:
                field.widget.attrs = {}
            
            if 'class' not in field.widget.attrs and not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = 'form-control'


class SavedSearchForm(forms.ModelForm):
    """Form for saving searches"""
    class Meta:
        model = SavedSearch
        fields = ['name', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Name this search'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if len(name) < 3:
            raise forms.ValidationError("Search name must be at least 3 characters long")
        return name


class FileIndexForm(forms.Form):
    """Form for manual indexing of files"""
    file_id = forms.IntegerField(widget=forms.HiddenInput())
    reindex = forms.BooleanField(required=False, initial=True, widget=forms.HiddenInput())