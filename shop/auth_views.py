from django.conf import settings
from django.contrib.auth.views import LoginView
from django.shortcuts import resolve_url
from django.urls import reverse

from .admin_access import has_control_access


class UnifiedLoginView(LoginView):
    template_name = "registration/login.html"

    def get_success_url(self):
        redirect_url = self.get_redirect_url()
        if redirect_url:
            return redirect_url
        if has_control_access(self.request.user):
            return reverse("control_dashboard")
        return resolve_url(settings.LOGIN_REDIRECT_URL)
