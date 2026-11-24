import logging
import re
import time
import uuid

from app.logging_config import request_id_var

access_log = logging.getLogger("app")

valid_id = re.compile(
    r"^[A-Za-z0-9._-]{1,64}$"
)  # {1,64} between 1 and 64 chars, ^ start of str, $ end of str


class RequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(
        self, scope: dict, receive, send
    ):  # scope:info about connection/request, receive: receives incoming messages, send:sends outgoing messages

        if scope["type"] not in ("http", "websocket"):  # when its "lifespan"
            await self.app(scope, receive, send)
            return

        # handle HTTP request or ws conn
        # ASGI stores headers inside scope as a list of byte pairs
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        # rid= request_id
        rid = incoming if valid_id.match(incoming) else uuid.uuid4().hex

        scope.setdefault("state", {})["request_id"] = (
            rid  # if "state" exists all good otherwise use empty dict and set "request_id" to rid
        )

        token = request_id_var.set(
            rid
        )  # returns a token, which we'll later use to reset req_id to original one
        start, status = time.perf_counter(), 500

        async def send_wrapper(message: dict):
            nonlocal status  # modifying the variable from an enclosing function
            if message["type"] == "http.response.start":
                status = message["status"]

                # message["headers"]=[
                #     *message.get("headers",[]),
                #     (b"x-request-id",rid.encode())
                # ]

                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"x-request-id"  # no duplicate req id headers
                ]
                headers.append((b"x-request-id", rid.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

        finally:
            if scope["type"] == "http":
                access_log.info(
                    "request",
                    extra={
                        "request_id": rid,
                        "status": status,
                        "path": scope["path"],
                        "method": scope["method"],
                        "duration_ms": round((time.perf_counter() - start) * 1000),
                    },
                )

            request_id_var.reset(token)
