"""
Utility functions for search functionality.
"""

import os
import time
from django.db import transaction
from django.utils import timezone
from .models import FileIndex

def index_file(filename, file_path, attachment_id=None):
    """
    Index a file's contents for searching.
    Fixed version with transaction management and delay to prevent locking.
    
    Args:
        filename (str): Name of the file
        file_path (str): Path to the file
        attachment_id (int): ID of the associated FileAttachment object
    
    Returns:
        bool: True if indexing was successful, False otherwise
    """
    try:
        # Small delay to prevent database locks when multiple operations happen
        time.sleep(0.1)
        
        # Use transaction.atomic() to properly isolate this operation
        with transaction.atomic():
            # Check if file exists and is readable
            if not os.path.exists(file_path) or not os.access(file_path, os.R_OK):
                print(f"File does not exist or is not readable: {file_path}")
                return False
            
            # Read file contents
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try reading as binary if UTF-8 fails
                try:
                    with open(file_path, 'rb') as f:
                        content = str(f.read())
                except:
                    print(f"Could not read file contents: {file_path}")
                    return False
            
            # Delete existing index for this file if it exists
            FileIndex.objects.filter(filename=filename).delete()
            
            # Create new index
            index = FileIndex(
                filename=filename,
                content=content,
                indexed_at=timezone.now(),
                file_attachment_id=attachment_id
            )
            index.save()
            
            return True
    
    except Exception as e:
        print(f"Error indexing file {filename}: {e}")
        return False