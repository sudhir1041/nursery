from django.test import TestCase
from django.contrib.auth import get_user_model

from .models import UserSetting


class UserSettingModelTests(TestCase):
    def test_create_setting(self):
        user = get_user_model().objects.create(username="tester")
        setting = UserSetting.objects.create(user=user, key="api_token", value="123")
        self.assertEqual(setting.key, "api_token")
        self.assertEqual(setting.value, "123")
