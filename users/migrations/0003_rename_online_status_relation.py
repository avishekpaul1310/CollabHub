from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0002_onlinestatus'),
    ]

    operations = [
        migrations.AlterField(
            model_name='onlinestatus',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='users_online_status', to=settings.AUTH_USER_MODEL),
        ),
    ]
