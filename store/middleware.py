from django.shortcuts import redirect
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.utils.deprecation import MiddlewareMixin


class PrivateHtmlCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get("Content-Type", "").lower().startswith("text/html"):
            patch_cache_control(response, private=True, no_store=True, max_age=0)
            patch_vary_headers(response, ("Cookie",))
        return response


class StorefrontLoginRequiredMiddleware(MiddlewareMixin):
    guest_routes = {"home", "login", "robots"}

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if (
            not match
            or match.app_name != "store"
            or match.url_name in self.guest_routes
            or request.session.get("customer_id")
        ):
            return None
        return redirect("store:login")