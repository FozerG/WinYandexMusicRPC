import atexit
import faulthandler
import logging
import sys
import threading
from pathlib import Path

from .config import data_directory

SESSION_MARKER = "=== WinYandexMusicRPC session started ==="
_configured = False


def rotate_session_logs(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    current = directory / "rpc.log"
    if current.exists():
        content = current.read_text(encoding="utf-8", errors="replace")
        marker = content.rfind(SESSION_MARKER)
        if marker >= 0:
            start = content.rfind("\n", 0, marker) + 1
            content = content[start:]
        temporary = directory / "rpc.log.tmp"
        temporary.write_text(content.rstrip("\n") + "\n\n", encoding="utf-8")
        temporary.replace(current)
    return current


def _unhandled_exception(exc_type, value, traceback):
    logging.getLogger(__name__).critical(
        "Unhandled exception", exc_info=(exc_type, value, traceback)
    )


def _thread_exception(args):
    logging.getLogger(__name__).critical(
        "Unhandled exception in thread %s",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    handler = logging.FileHandler(rotate_session_logs(data_directory()), encoding="utf-8")
    handlers = [handler]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger("yandex_music").setLevel(logging.CRITICAL)
    logging.getLogger(__name__).info(SESSION_MARKER)
    sys.excepthook = _unhandled_exception
    threading.excepthook = _thread_exception
    faulthandler.enable(file=handler.stream, all_threads=True)
    atexit.register(faulthandler.disable)
    _configured = True
