"""Bounded HTTP workers and an OS-backed lease for a classroom data directory."""
import os
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer as StandardThreadingHTTPServer


class ThreadingHTTPServer(StandardThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128

    def __init__(self, *args, max_workers=128, **kwargs):
        self._slots = threading.BoundedSemaphore(max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                # Consume the already sent header before closing; on Windows
                # closing with unread input can discard the 503 with a reset.
                request.settimeout(.1)
                try:
                    request.recv(65536)
                except OSError:
                    pass
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\nRetry-After: 1\r\n\r\n")
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


@contextmanager
def data_lease(directory):
    directory.parent.mkdir(parents=True, exist_ok=True)
    with (directory.parent / ("."+directory.name+".server.lock")).open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if not lock.tell():
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("Dữ liệu đang được server hoặc công cụ bảo trì khác sử dụng. Hãy dừng tiến trình đó trước.") from error
        try:
            directory.mkdir(parents=True, exist_ok=True)
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
