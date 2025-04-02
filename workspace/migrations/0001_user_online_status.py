# Generated manually to fix migration issues

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('workspace', '0001_initial'),  # Assuming 0001_initial exists and creates other models
    ]

    operations = [
        migrations.CreateModel(
            name='UserOnlineStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('online', 'Online'), ('away', 'Away'), ('afk', 'AFK'), 
                                            ('offline', 'Offline'), ('break', 'On Break'), 
                                            ('outside-hours', 'Outside Working Hours')], default='offline', max_length=20)),
                ('status_message', models.CharField(blank=True, max_length=255, null=True)),
                ('last_activity', models.DateTimeField(auto_now=True)),
                ('device_info', models.JSONField(blank=True, default=dict)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, 
                                             related_name='workspace_online_status', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'User Online Statuses',
            },
        ),
    ]
