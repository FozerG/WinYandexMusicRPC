"""One thumbnail read on an isolated MTA thread, using existing GSMTC metadata."""

import asyncio

MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024


async def _read(properties):
    from winrt.windows.storage.streams import DataReader

    reference = properties.thumbnail
    if reference is None:
        return None
    stream = await reference.open_read_async()
    try:
        size = stream.size
        if not size:
            return None
        if size > MAX_THUMBNAIL_BYTES:
            raise ValueError("Windows thumbnail exceeds 8 MiB")
        reader = DataReader(stream)
        try:
            loaded = await reader.load_async(size)
            if loaded != size:
                raise ValueError("Incomplete Windows thumbnail")
            data = bytearray(loaded)
            reader.read_bytes(data)
            return bytes(data)
        finally:
            reader.detach_stream()
            reader.close()
    finally:
        stream.close()


def read_thumbnail(properties):
    # The agile properties object can be read on this isolated MTA thread.
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
    try:
        return asyncio.run(_read(properties))
    finally:
        pythoncom.CoUninitialize()


def normalize_thumbnail(data: bytes) -> bytes:
    """Decode actual image bytes, bound dimensions, strip metadata, encode JPEG."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
    from PyQt6.QtGui import QImageReader

    if not data or len(data) > MAX_THUMBNAIL_BYTES:
        raise ValueError("Invalid thumbnail size")
    source = QBuffer()
    source.setData(QByteArray(data))
    source.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(source)
    size = reader.size()
    if not size.isValid() or max(size.width(), size.height()) > 4096:
        raise ValueError("Invalid or oversized thumbnail dimensions")
    size.scale(QSize(512, 512), Qt.AspectRatioMode.KeepAspectRatio)
    reader.setScaledSize(size)
    image = reader.read()
    if image.isNull():
        raise ValueError("Windows did not provide a decodable image")
    output = QBuffer()
    output.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(output, "JPEG", 88):
        raise ValueError("Cannot encode thumbnail")
    return bytes(output.data())
