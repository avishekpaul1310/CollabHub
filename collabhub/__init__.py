import os
import sys

# Fix for libmagic on Windows
if sys.platform.startswith('win'):
    try:
        import magic
        # Path to python-magic-bin's DLL
        dll_path = os.path.join(os.path.dirname(magic.__file__), 'libmagic')
        # Add to path if it exists
        if os.path.exists(dll_path):
            os.environ['PATH'] = dll_path + os.pathsep + os.environ['PATH']
    except ImportError:
        pass

# Import the celery app
from .celery import app as celery_app

# Make the app available at module level
__all__ = ('celery_app',)
