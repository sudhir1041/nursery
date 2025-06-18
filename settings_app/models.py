from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet


class EncryptedTextField(models.TextField):
    """A TextField that transparently encrypts its value using Fernet."""

    def _get_fernet(self) -> Fernet:
        key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
        if not key:
            raise ValueError("FIELD_ENCRYPTION_KEY must be set in settings")
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        f = self._get_fernet()
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            return value

    def get_prep_value(self, value):
        if value is None:
            return value
        f = self._get_fernet()
        return f.encrypt(str(value).encode()).decode()


class ProjectSetting(models.Model):
    """Stores credentials and webhook paths for external integrations."""

    service_name = models.CharField(max_length=100, unique=True)
    api_key = EncryptedTextField()
    webhook_path = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Project Setting"
        verbose_name_plural = "Project Settings"

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return self.service_name

    @property
    def full_webhook_url(self) -> str:
        base = getattr(settings, "BASE_WEBHOOK_URL", "")
        return f"{base.rstrip('/')}{self.webhook_path}" if base else self.webhook_path

