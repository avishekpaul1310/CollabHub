from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workspace', '0005_notification_priority_breakevent'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreference',
            name='muted_threads',
            field=models.ManyToManyField(blank=True, related_name='muted_by_users', to='workspace.thread'),
        ),
    ]
