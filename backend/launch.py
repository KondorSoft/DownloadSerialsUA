from __future__ import annotations

import secrets
import socket
import threading
import webbrowser

import uvicorn

from app.main import create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    token = secrets.token_urlsafe(32)
    port = free_port()
    url = f"http://127.0.0.1:{port}/?token={token}"
    app = create_app(token=token)
    print(f"Кадр запущено: {url}", flush=True)
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
