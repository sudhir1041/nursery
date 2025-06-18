from django.db import migrations, models
import settings_app.models

class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ProjectSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_name', models.CharField(max_length=100, unique=True)),
                ('api_key', settings_app.models.EncryptedTextField()),
                ('webhook_path', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Project Setting',
                'verbose_name_plural': 'Project Settings',
            },
        ),
    ]

