from slowapi import Limiter
from starlette.requests import Request


def client_ip(request: Request) -> str:
    # Render's proxy adds the real client IP as the LAST entry in X-Forwarded-For.
    # Earlier entries are supplied by the client and can be faked, so use the last one.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip)