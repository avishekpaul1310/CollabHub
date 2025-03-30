from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
import json

class SavedSearch(models.Model):
    """Model for storing user's saved searches"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_searches')
    name = models.CharField(max_length=100)
    query = models.CharField(max_length=255)  # The search query string
    filters = models.TextField()  # JSON string of filter parameters
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    is_default = models.BooleanField(default=False)  # Whether this is the user's default search
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = "Saved searches"
    
    def __str__(self):
        return f"{self.user.username}: {self.name}"
    
    def save(self, *args, **kwargs):
        # Generate a unique slug if not provided
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            n = 1
            while SavedSearch.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
            
        # Ensure proper JSON format for filters
        if isinstance(self.filters, dict):
            self.filters = json.dumps(self.filters)
            
        super().save(*args, **kwargs)
        
        # If this is set as default, unset any other defaults for this user
        if self.is_default:
            SavedSearch.objects.filter(
                user=self.user, 
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
    
    def get_filters(self):
        """Return filters as a Python dictionary"""
        try:
            return json.loads(self.filters)
        except (ValueError, TypeError):
            return {}


class SearchLog(models.Model):
    """Model for tracking search history and popularity"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_history')
    query = models.CharField(max_length=255)
    filters = models.TextField(blank=True)  # JSON string of filter parameters
    results_count = models.IntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username}: {self.query} ({self.timestamp})"
    
    def get_filters(self):
        """Return filters as a Python dictionary"""
        try:
            return json.loads(self.filters)
        except (ValueError, TypeError):
            return {}


class FileIndex(models.Model):
    """Model for storing extracted text content from files for searching"""
    file = models.OneToOneField('workspace.FileAttachment', on_delete=models.CASCADE, related_name='index')
    extracted_text = models.TextField(blank=True)
    indexed_at = models.DateTimeField(auto_now=True)
    file_type = models.CharField(max_length=50, blank=True)
    
    class Meta:
        verbose_name_plural = "File indices"
    
    def __str__(self):
        return f"Index for {self.file.name}"