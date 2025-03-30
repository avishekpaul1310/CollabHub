from django.core.management.base import BaseCommand, CommandError
from search.indexing import index_all_files, reindex_file
from workspace.models import FileAttachment
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Index or reindex files for search functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Index all unindexed files',
        )
        parser.add_argument(
            '--reindex',
            action='store_true',
            help='Reindex already indexed files',
        )
        parser.add_argument(
            '--file-id',
            type=int,
            help='ID of a specific file to (re)index',
        )

    def handle(self, *args, **options):
        start_time = time.time()

        if options['file_id']:
            file_id = options['file_id']
            try:
                file = FileAttachment.objects.get(id=file_id)
                self.stdout.write(f"Processing file: {file.name}")
                success = reindex_file(file_id)
                if success:
                    self.stdout.write(self.style.SUCCESS(f"Successfully indexed file {file.name}"))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to index file {file.name}"))
            except FileAttachment.DoesNotExist:
                raise CommandError(f'File with ID {file_id} does not exist')

        elif options['all']:
            # Process all unindexed files
            self.stdout.write("Indexing all unindexed files...")
            indexed_count, failed_count = index_all_files()
            self.stdout.write(self.style.SUCCESS(
                f"Indexing complete: {indexed_count} files indexed, {failed_count} failed"
            ))

        elif options['reindex']:
            # Reindex all files
            self.stdout.write("Reindexing all files...")
            # Get all files
            files = FileAttachment.objects.all()
            
            indexed_count = 0
            failed_count = 0
            
            for file in files:
                self.stdout.write(f"Processing file: {file.name}")
                success = reindex_file(file.id)
                if success:
                    indexed_count += 1
                    self.stdout.write(f"Indexed: {file.name}")
                else:
                    failed_count += 1
                    self.stdout.write(self.style.WARNING(f"Failed: {file.name}"))
            
            self.stdout.write(self.style.SUCCESS(
                f"Reindexing complete: {indexed_count} files indexed, {failed_count} failed"
            ))
        
        else:
            self.stdout.write(self.style.WARNING(
                "No action specified. Use --all to index all files, --reindex to reindex all files, "
                "or --file-id to index a specific file."
            ))
        
        # Calculate execution time
        execution_time = time.time() - start_time
        self.stdout.write(f"Execution time: {execution_time:.2f} seconds")