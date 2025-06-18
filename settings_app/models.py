from django.db import models
from django.contrib.auth import get_user_model


class UserSetting(models.Model):
    """Key/value configuration data stored per user."""

    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    key = models.CharField(max_length=255)
    value = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "key")
        verbose_name = "User Setting"
        verbose_name_plural = "User Settings"

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"{self.user.username}: {self.key}"

