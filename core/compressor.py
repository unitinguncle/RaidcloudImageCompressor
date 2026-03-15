"""
core/compressor.py — Async-like image compression in a QThread.
Ported + enhanced from unitinguncle/RaidcloudImageCompressor.
"""

import concurrent.futures
import io
import logging
import os
import time

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


def _compress_worker(
    file_path: str,
    output_folder: str,
    output_format: str,
    jpeg_quality: int,
    png_compression: int,
    preserve_exif: bool,
    max_retries: int = 3,
):
    """
    Worker function meant for ProcessPoolExecutor.
    Must be top-level so it can be pickled.
    Returns (filename, bool success, message string).
    """
    filename = os.path.basename(file_path)
    stem, _ = os.path.splitext(filename)
    ext_out = "jpg" if output_format == "JPEG" else "png"
    out_name = f"{stem}_C.{ext_out}"
    out_path = os.path.join(output_folder, out_name)

    RAW_EXTENSIONS = (
        ".cr2", ".cr3", ".nef", ".nrw",
        ".arw", ".sr2", ".srf", ".dng",
    )

    for attempt in range(max_retries):
        try:
            with open(file_path, "rb") as f:
                data = f.read()

            img = Image.open(io.BytesIO(data))

            exif_bytes = None
            if preserve_exif:
                img.load()  # force full decode so img.info["exif"] is populated
                exif_bytes = img.info.get("exif")

            is_raw = os.path.splitext(filename)[1].lower() in RAW_EXTENSIONS
            if is_raw or img.mode not in ("RGB", "RGBA", "L", "CMYK"):
                img = img.convert("RGB")
            elif img.mode == "RGBA" and output_format == "JPEG":
                img = img.convert("RGB")

            save_kwargs: dict = {
                "format": output_format,
                "optimize": True,
            }
            if output_format == "JPEG":
                save_kwargs["quality"] = jpeg_quality
                if exif_bytes:
                    save_kwargs["exif"] = exif_bytes
            else:
                save_kwargs["compress_level"] = png_compression

            img.save(out_path, **save_kwargs)
            # Return the actual output path so the caller can track it without parsing strings
            return (filename, True, out_path, "")

        except Exception as exc:
            if attempt == max_retries - 1:
                return (filename, False, "", str(exc))
            else:
                time.sleep(2 ** attempt)
                
    return (filename, False, "", "Process failed silently")


class CompressorThread(QThread):
    """
    Compresses all images in a source folder and saves them to an output folder.
    Uses ProcessPoolExecutor to compress multiple files concurrently across CPU cores.

    Signals:
        progress(int)                    — 0-100 overall %
        file_done(filename, ok, message) — per-file result
        finished()
    """

    progress  = Signal(int)
    file_done = Signal(str, bool, str, str)  # (filename, ok, out_path, error_msg)
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
        files = []
        for root, _, names in os.walk(self.source_folder):
            for name in names:
                if os.path.splitext(name)[1].lower() in VALID_IMAGE_EXTENSIONS:
                    files.append(os.path.join(root, name))

        if not files:
            self.finished.emit()
            return

        os.makedirs(self.output_folder, exist_ok=True)
        total = len(files)

        # Limit to 4 workers to prevent OOM on high-core-count machines (e.g. M-series Mac)
        max_workers = min(4, os.cpu_count() or 1)
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            
            for file_path in files:
                futures.append(
                    executor.submit(
                        _compress_worker,
                        file_path,
                        self.output_folder,
                        self.output_format,
                        self.jpeg_quality,
                        self.png_compression,
                        self.preserve_exif,
                    )
                )

            completed = 0
            # iterate as they complete rather than in submission order
            for future in concurrent.futures.as_completed(futures):
                if self._cancel:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                    
                filename, ok, out_path, err_msg = future.result()
                self.file_done.emit(filename, ok, out_path, err_msg)
                
                completed += 1
                self.progress.emit(int((completed / total) * 100))

        self.finished.emit()
