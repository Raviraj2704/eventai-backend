from slowapi import Limiter
from starlette.requests import Request

def client_ip(request: Request) -> str:
    # Render appends proxy hops to X-Forwarded-For, so the real client is the FIRST entry.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=client_ip)