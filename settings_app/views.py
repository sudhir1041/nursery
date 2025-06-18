from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .models import UserSetting
from .forms import UserSettingForm


@login_required
def user_settings(request):
    """View for listing and adding user specific configuration."""

    settings_qs = UserSetting.objects.filter(user=request.user)

    if request.method == "POST":
        form = UserSettingForm(request.POST)
        if form.is_valid():
            UserSetting.objects.update_or_create(
                user=request.user,
                key=form.cleaned_data["key"],
                defaults={"value": form.cleaned_data["value"]},
            )
            return redirect("user_settings")
    else:
        form = UserSettingForm()

    return render(
        request,
        "settings_app/user_settings.html",
        {"form": form, "user_settings": settings_qs},
    )

