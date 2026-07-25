"""Baseline security response headers -- the FastAPI/Starlette-native
equivalent of the spec's "Helmet-equivalent" requirement (Helmet is an
Express/Node middleware; there's no direct port, so this reimplements the
handful of headers that actually matter for an API service, skipping the
browser-page-specific ones Helmet also sets, like CSP's script-src, which
don't apply to a JSON API with no rendered HTML).

Always on -- purely additive response headers, can't break any existing
behavior or test."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        # HSTS only makes sense once TLS terminates in front of this
        # service (it tells browsers to *only* ever use HTTPS) -- setting
        # it unconditionally in a dev/plain-HTTP setup would be misleading.
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
