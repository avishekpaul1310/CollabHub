from django.db import migrations, models
import django.db.models.deletion

def create_default_threads(apps, schema_editor):
    """Create a default thread for each work item and move messages to it"""
    WorkItem = apps.get_model('workspace', 'WorkItem')
    Thread = apps.get_model('workspace', 'Thread')
    Message = apps.get_model('workspace', 'Message')
    
    # For each work item, create a default thread
    for work_item in WorkItem.objects.all():
        # Create default thread
        thread = Thread.objects.create(
            work_item=work_item,
            title=f"General Discussion: {work_item.title}",
            created_by=work_item.owner,
            is_public=True
        )
        
        # Move all messages from this work item to the new thread
        for message in Message.objects.filter(work_item=work_item):
            message.thread = thread
            # Keep the parent reference intact for threaded messages
            message.save()


class Migration(migrations.Migration):

    dependencies = [
        ('workspace', '0007_remove_message_work_item_message_is_thread_starter_and_more'),
    ]

    operations = [
        # 1. Add Thread model
        migrations.CreateModel(
            name='Thread',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_public', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_threads', to='auth.user')),
                ('work_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='threads', to='workspace.workitem')),
                ('allowed_users', models.ManyToManyField(blank=True, related_name='accessible_threads', to='auth.user')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        
        # 2. Add thread field to Message
        migrations.AddField(
            model_name='message',
            name='thread',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='workspace.thread'),
        ),
        
        # 3. Run data migration to create threads and update messages
        migrations.RunPython(create_default_threads),
        
        # 4. Make thread field required and remove work_item field
        migrations.AlterField(
            model_name='message',
            name='thread',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='workspace.thread'),
        ),
        migrations.RemoveField(
            model_name='message',
            name='work_item',
        ),
    ]
