"""Run the deployable ASGI service; PORT is honored explicitly."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "briefledger.app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        access_log=False,
    )
