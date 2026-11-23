"""Bind management API requests to the identity established by password login."""
import hmac
import os
from starlette.responses import JSONResponse


class ManagementSessionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").rstrip("/")
        public = path in {"/api/users/login", "/api/users/logout", "/api/auth/login", "/api/auth/verify-invite-code"} or path.startswith((
            "/api/service/", "/api/autobi/share/", "/api/xlsx-qa/share/", "/api/eval/share/",
        ))
        if scope["type"] == "http" and path.startswith("/api/") and not public:
            if path == "/api/autobi/gateway/v2/lab" and scope.get("method") == "POST":
                expected = os.getenv("GILEAD_LAB_SERVICE_TOKEN", "").encode()
                supplied = dict(scope["headers"]).get(b"x-internal-token", b"")
                if expected and hmac.compare_digest(supplied, expected):
                    return await self.app(scope, receive, send)
            user_id = scope["session"].get("user_id")
            if not user_id:
                response = JSONResponse({"code": "UNAUTHORIZED", "message": "请先登录平台", "data": None}, status_code=401)
                return await response(scope, receive, send)
            headers = [(k, v) for k, v in scope["headers"] if k.lower() not in {b"x-user-id", b"x-username"}]
            headers.append((b"x-user-id", str(user_id).encode("ascii")))
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)
