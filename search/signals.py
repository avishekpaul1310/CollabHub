from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from workspace.models import FileAttachment
from .models import FileIndex
from .indexing import index_file
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=FileAttachment)
def create_file_index(sender, instance, created, **kwargs):
    """Index a file when it is first created"""
    if created:
        try:
            # Run indexing in background for production
            from django.core.management import call_command
            from threading import Thread
            
            def index_file_task():
                try:
                    success = index_file(instance)
                    if not success:
                        logger.warning(f"Failed to index file: {instance.name}")
                except Exception as e:
                    logger.error(f"Error indexing file {instance.name}: {str(e)}")
            
            # Run in a separate thread to not block the main thread
            thread = Thread(target=index_file_task)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            logger.error(f"Error starting indexing thread for {instance.name}: {str(e)}")

@receiver(post_delete, sender=FileAttachment)
def delete_file_index(sender, instance, **kwargs):
    """Delete file index when file is deleted"""
    try:
        FileIndex.objects.filter(file=instance).delete()
    except Exception as e:
        logger.error(f"Error deleting file index for {instance.name}: {str(e)}")