"""ASGI request limits and response security, including mounted tool transports."""

import time
from ipaddress import ip_address, ip_network
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse


class Boundary:
    def __init__(self, app, settings, requests, latency):
        self.app, self.settings, self.requests, self.latency = app, settings, requests, latency

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        client = scope.get("client")

        async def reject(code, message, status):
            await JSONResponse({"error": {"code": code, "message": message}}, status_code=status)(
                scope, receive, send
            )

        if (
            client
            and client[0] != "testclient"
            and not any(
                ip_address(client[0]) in ip_network(cidr)
                for cidr in self.settings.allowed_client_cidrs
            )
        ):
            await reject("LOCAL_ONLY", "This release accepts loopback clients only.", 403)
            return
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            if headers.get("origin") and headers["origin"] not in self.settings.allowed_origins:
                await reject("ORIGIN_DENIED", "Origin not allowed.", 403)
                return
            body = bytearray()
            while True:
                chunk = await receive()
                if chunk["type"] == "http.disconnect":
                    return
                body.extend(chunk.get("body", b""))
                maximum = (
                    1_440_044 if scope.get("path") == "/api/v1/pharmacy/voice/transcribe" else 65536
                )
                if len(body) > maximum:
                    await reject(
                        "REQUEST_TOO_LARGE", "Request exceeds the endpoint body limit.", 413
                    )
                    return
                if not chunk.get("more_body", False):
                    break
            original_receive = receive
            delivered = False

            async def replay_body():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = replay_body
        request_id = str(uuid4())
        started = time.monotonic()
        status = 500
        scope.setdefault("state", {})["request_id"] = request_id

        async def secured(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers.update(
                    {
                        "X-Request-ID": request_id,
                        "X-Content-Type-Options": "nosniff",
                        "Referrer-Policy": "no-referrer",
                        "Cache-Control": "no-store",
                        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'",
                    }
                )
            await send(message)

        try:
            await self.app(scope, receive, secured)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            self.requests.labels(scope["method"], route, str(status)).inc()
            self.latency.labels(route).observe(time.monotonic() - started)
