import base64
from typing import Callable

import grpc


class BasicAuthInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, valid_credentials: dict):
        self.valid_credentials = valid_credentials

    def _decode_basic_auth(self, auth_header: str) -> tuple:
        try:
            encoded_credentials = auth_header.split(" ")[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
            return username, password
        except Exception:
            return None, None

    async def intercept_service(self, continuation: Callable, handler_call_details):
        # Get metadata
        metadata = dict(handler_call_details.invocation_metadata)

        # Check auth header
        auth_header = metadata.get("authorization", "")

        if not auth_header.startswith("Basic "):
            context = grpc.aio.ServicerContext()
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing or invalid authorization header",
            )

        # Decode auth header
        username, password = self._decode_basic_auth(auth_header)

        if not username or not password:
            context = grpc.aio.ServicerContext()
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED, "Invalid authorization format"
            )

        # Check credentials
        credential_key = f"{username}:{password}"
        if credential_key not in self.valid_credentials:
            context = grpc.aio.ServicerContext()
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")

        # If valid, continue
        return await continuation(handler_call_details)
