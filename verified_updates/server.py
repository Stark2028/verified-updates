"""Small real HTTP repository for local experiments; never serves publisher keys."""

from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass


@contextmanager
def serve_directory(directory: Path, port: int = 0) -> Iterator[str]:
    handler = partial(QuietHandler, directory=str(directory.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

