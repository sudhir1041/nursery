from django.db import models

class IntegrationSetting(models.Model):
    """Store credentials for external integrations."""
    service = models.CharField(max_length=100, unique=True)
    credentials = models.JSONField(default=dict)

    def __str__(self):
        return self.service
