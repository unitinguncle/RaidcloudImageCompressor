"""
core/compressor.py — Async-like image compression in a QThread.
Ported + enhanced from unitinguncle/RaidcloudImageCompressor.
"""

import asyncio
import io
import logging
import os
import time

import aiofiles
from PIL import Image

from PySide6.QtCore import QThread, Signal

VALID_IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg",
    ".cr2", ".cr3",
    ".nef", ".nrw",
    ".arw", ".sr2", ".srf",
    ".dng",
)

RAW_EXTENSIONS = (
    ".cr2", ".cr3", ".nef", ".nrw",
    ".arw", ".sr2", ".srf", ".dng",
)


def estimate_compressed_size(
    folder: str,
    output_format: str,
    jpeg_quality: int,
    png_compression: int,
) -> tuple[int, int]:
    """
    Quick estimation: sample up to 5 files and extrapolate.
    Returns (estimated_bytes, total_file_count).
    """
    files = [
        os.path.join(root, f)
        for root, _, names in os.walk(folder)
        for f in names
        if os.path.splitext(f)[1].lower() in VALID_IMAGE_EXTENSIONS
    ]
    if not files:
        return 0, 0

    sample = files[:5]
    sample_orig = sum(os.path.getsize(p) for p in sample)
    sample_compressed = 0
    for path in sample:
        try:
            img = Image.open(path)
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            if output_format == "JPEG":
                img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
            else:
                img.save(buf, format="PNG", compress_level=png_compression, optimize=True)
            sample_compressed += buf.tell()
        except Exception:
            sample_compressed += os.path.getsize(path)

    ratio = sample_compressed / max(sample_orig, 1)
    total_orig = sum(os.path.getsize(p) for p in files)
    return int(total_orig * ratio), len(files)


class CompressorThread(QThread):
    """
    Compresses all images in a source folder and saves them to an output folder.

    Signals:
        progress(int)                    — 0-100 overall %
        file_done(filename, ok, message) — per-file result
        finished()
    """

    progress  = Signal(int)
    file_done = Signal(str, bool, str)   # filename, success, message
    finished  = Signal()

    def __init__(
        self,
        source_folder: str,
        output_folder: str,
        output_format: str = "JPEG",
        jpeg_quality: int = 85,
        png_compression: int = 6,
        preserve_exif: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.source_folder   = source_folder
        self.output_folder   = output_folder
        self.output_format   = output_format
        self.jpeg_quality    = jpeg_quality
        self.png_compression = png_compression
        self.preserve_exif   = preserve_exif
        self._cancel         = False

    def cancel(self):
        self._cancel = True

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._compress_all())
        finally:
            loop.close()
            self.finished.emit()

    async def _compress_all(self):
        files = []
        for root, _, names in os.walk(self.source_folder):
            for name in names:
                if os.path.splitext(name)[1].lower() in VALID_IMAGE_EXTENSIONS:
                    files.append(os.path.join(root, name))

        if not files:
            return

        os.makedirs(self.output_folder, exist_ok=True)
        total = len(files)

        for idx, file_path in enumerate(files):
            if self._cancel:
                break
            await self._compress_one(file_path)
            self.progress.emit(int((idx + 1) / total * 100))

    async def _compress_one(self, file_path: str, max_retries: int = 3):
        filename = os.path.basename(file_path)
        stem, _ = os.path.splitext(filename)
        ext_out = "jpg" if self.output_format == "JPEG" else "png"
        out_name = f"{stem}_C.{ext_out}"
        out_path = os.path.join(self.output_folder, out_name)

        for attempt in range(max_retries):
            try:
                async with aiofiles.open(file_path, "rb") as f:
                    data = await f.read()

                img = Image.open(io.BytesIO(data))

                # Extract EXIF before any conversion
                exif_bytes = None
                if self.preserve_exif:
                    exif_bytes = img.info.get("exif")

                # RAW → RGB; other modes normalise
                is_raw = os.path.splitext(filename)[1].lower() in RAW_EXTENSIONS
                if is_raw or img.mode not in ("RGB", "RGBA", "L", "CMYK"):
                    img = img.convert("RGB")
                elif img.mode == "RGBA" and self.output_format == "JPEG":
                    img = img.convert("RGB")

                save_kwargs: dict = {
                    "format": self.output_format,
                    "optimize": True,
                }
                if self.output_format == "JPEG":
                    save_kwargs["quality"] = self.jpeg_quality
                    if exif_bytes:
                        save_kwargs["exif"] = exif_bytes
                else:
                    save_kwargs["compress_level"] = self.png_compression

                img.save(out_path, **save_kwargs)
                self.file_done.emit(filename, True, f"→ {out_name}")
                return

            except Exception as exc:
                if attempt == max_retries - 1:
                    self.file_done.emit(filename, False, str(exc))
                else:
                    await asyncio.sleep(2 ** attempt)
