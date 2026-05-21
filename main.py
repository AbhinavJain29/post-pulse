"""
Entry point for Post Pulse.
Finds a free port, starts uvicorn, and opens the browser.
"""
import socket
import time
import threading
import webbrowser

import uvicorn

from api.server import app


def _find_free_port(start: int = 8080, end: int = 8084) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}–{end}.")


def _open_browser(url: str, delay: float = 1.5) -> None:
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    port = _find_free_port()
    url = f"http://localhost:{port}"
    print(f"\n  Post Pulse → {url}\n")
    _open_browser(url)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
