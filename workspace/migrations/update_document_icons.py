from django.db import migrations

def update_document_icons(apps, schema_editor):
    """
    Update all document type icons from fa-file-alt to fa-file-lines
    This improves visibility on white backgrounds
    """
    # Get the models
    WorkItemType = apps.get_model('workspace', 'WorkItemType')
    
    # Update all document types with the new icon
    WorkItemType.objects.filter(icon='fa-file-alt').update(icon='fa-file-lines')

    # Also update any with name similar to 'document' or 'doc'
    WorkItemType.objects.filter(name__icontains='document', icon='fa-file-alt').update(icon='fa-file-lines')
    WorkItemType.objects.filter(name__icontains='doc', icon='fa-file-alt').update(icon='fa-file-lines')
    
    print("Document icons updated from fa-file-alt to fa-file-lines for better visibility")

class Migration(migrations.Migration):
    dependencies = [
        ('workspace', '0003_alter_workitem_type_workitemtype_workitem_item_type'),  # Updated to latest migration
    ]

    operations = [
        migrations.RunPython(update_document_icons),
    ]