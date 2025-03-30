from django import template
import re

register = template.Library()

@register.filter
def split(value, delimiter):
    """Split a string with the given delimiter and return the list"""
    return value.split(delimiter)

@register.filter
def highlight(text, query):
    """Highlight query terms in the given text"""
    if not query or not text:
        return text
    
    # Convert text to string if it's not already
    text = str(text)
    
    # Split query into terms
    query_terms = query.lower().split()
    
    # Create regex pattern that matches any of the query terms
    # with word boundary to match whole words only
    pattern = r'\b(' + '|'.join(re.escape(term) for term in query_terms) + r')\b'
    
    # Replace matched terms with highlighted version
    highlighted = re.sub(
        pattern,
        r'<span class="highlight">\1</span>',
        text,
        flags=re.IGNORECASE
    )
    
    return template.mark_safe(highlighted)

@register.filter
def truncate_middle(text, length):
    """Truncate text in the middle, preserving start and end"""
    if not text or len(text) <= length:
        return text
    
    # Determine length of start and end portions
    half_length = (length - 3) // 2
    
    # Truncate in the middle
    return text[:half_length] + '...' + text[-half_length:]

@register.filter
def file_icon_class(filename):
    """Return appropriate Font Awesome icon class based on file extension"""
    if not filename:
        return 'fa-file'
    
    extension = filename.split('.')[-1].lower()
    
    if extension in ['doc', 'docx', 'odt', 'rtf']:
        return 'fa-file-word text-primary'
    elif extension in ['xls', 'xlsx', 'csv']:
        return 'fa-file-excel text-success'
    elif extension in ['ppt', 'pptx']:
        return 'fa-file-powerpoint text-warning'
    elif extension == 'pdf':
        return 'fa-file-pdf text-danger'
    elif extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg']:
        return 'fa-file-image text-info'
    elif extension in ['zip', 'rar', 'tar', 'gz', '7z']:
        return 'fa-file-archive text-secondary'
    elif extension in ['mp3', 'wav', 'ogg']:
        return 'fa-file-audio text-warning'
    elif extension in ['mp4', 'avi', 'mov', 'wmv']:
        return 'fa-file-video text-danger'
    elif extension in ['html', 'htm', 'xml', 'css', 'js', 'py', 'java', 'c', 'cpp', 'cs', 'php', 'rb']:
        return 'fa-file-code text-primary'
    elif extension == 'txt':
        return 'fa-file-alt text-secondary'
    else:
        return 'fa-file text-muted'