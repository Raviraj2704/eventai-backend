from slowapi import Limiter
from starlette.requests import Request


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    key = forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "unknown")
    print(f"RATE_DEBUG xff={forwarded!r} key={key!r}", flush=True)
    return key


limiter = Limiter(key_func=client_ip)