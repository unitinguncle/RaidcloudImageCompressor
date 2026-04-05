"""
core/config.py — QSettings-based configuration for RaidCloud Immich Suite.
Extended with RustFS, CompreFace, and FaceDB settings.
"""

from PySide6.QtCore import QSettings



class AppConfig:
    """Typed wrapper around QSettings for all persistent app settings."""

    ORG  = "RaidCloud"
    APP  = "ImmichSuite"

    def __init__(self):
        self._s = QSettings(self.ORG, self.APP)
        self._api_key = ""
        self._rustfs_secret = ""   # never persisted
        self._cf_api_key    = ""   # never persisted
        # Aggressively delete any old plaintext key that might be stuck in QSettings
        if self._s.contains("connection/api_key"):
            self._s.remove("connection/api_key")

    # ── Connection ────────────────────────────────────────────────────────────
    @property
    def server_url(self) -> str:
        return self._s.value("connection/server_url", "https://photos.raidcloud.in", str)

    @server_url.setter
    def server_url(self, v: str):
        self._s.setValue("connection/server_url", v)

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, v: str):
        self._api_key = v

    # ── Compression ───────────────────────────────────────────────────────────
    @property
    def output_format(self) -> str:
        return self._s.value("compression/output_format", "JPEG", str)

    @output_format.setter
    def output_format(self, v: str):
        self._s.setValue("compression/output_format", v)

    @property
    def jpeg_quality(self) -> int:
        return int(self._s.value("compression/jpeg_quality", 85))

    @jpeg_quality.setter
    def jpeg_quality(self, v: int):
        self._s.setValue("compression/jpeg_quality", v)

    @property
    def png_compression(self) -> int:
        return int(self._s.value("compression/png_compression", 6))

    @png_compression.setter
    def png_compression(self, v: int):
        self._s.setValue("compression/png_compression", v)

    @property
    def preserve_exif(self) -> bool:
        val = self._s.value("compression/preserve_exif", True)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    @preserve_exif.setter
    def preserve_exif(self, v: bool):
        self._s.setValue("compression/preserve_exif", v)

    # ── Paths ─────────────────────────────────────────────────────────────────
    @property
    def last_source_folder(self) -> str:
        return self._s.value("paths/last_source_folder", "", str)

    @last_source_folder.setter
    def last_source_folder(self, v: str):
        self._s.setValue("paths/last_source_folder", v)

    @property
    def last_output_folder(self) -> str:
        return self._s.value("paths/last_output_folder", "", str)

    @last_output_folder.setter
    def last_output_folder(self, v: str):
        self._s.setValue("paths/last_output_folder", v)

    @property
    def last_takeout_path(self) -> str:
        return self._s.value("paths/last_takeout_path", "", str)

    @last_takeout_path.setter
    def last_takeout_path(self, v: str):
        self._s.setValue("paths/last_takeout_path", v)

    @property
    def binary_path_override(self) -> str:
        return self._s.value("paths/binary_path_override", "", str)

    @binary_path_override.setter
    def binary_path_override(self, v: str):
        self._s.setValue("paths/binary_path_override", v)

    # ── Advanced / immich-go ──────────────────────────────────────────────────
    @property
    def log_level(self) -> str:
        return self._s.value("advanced/log_level", "INFO", str)

    @log_level.setter
    def log_level(self, v: str):
        self._s.setValue("advanced/log_level", v)

    @property
    def timeout(self) -> int:
        return int(self._s.value("advanced/timeout", 1200))  # 20 min = immich-go default

    @timeout.setter
    def timeout(self, v: int):
        self._s.setValue("advanced/timeout", v)

    @property
    def recursive_upload(self) -> bool:
        val = self._s.value("advanced/recursive_upload", True)
        if isinstance(val, str):
            return val.lower() == "true"
        return bool(val)

    @recursive_upload.setter
    def recursive_upload(self, v: bool):
        self._s.setValue("advanced/recursive_upload", v)

    # ── RustFS (S3-compatible object storage on Unraid) ──────────────────────
    @property
    def rustfs_endpoint(self) -> str:
        return self._s.value("rustfs/endpoint", "", str)

    @rustfs_endpoint.setter
    def rustfs_endpoint(self, v: str):
        self._s.setValue("rustfs/endpoint", v)

    @property
    def rustfs_access_key(self) -> str:
        return self._s.value("rustfs/access_key", "", str)

    @rustfs_access_key.setter
    def rustfs_access_key(self, v: str):
        self._s.setValue("rustfs/access_key", v)

    @property
    def rustfs_secret_key(self) -> str:
        # Stored in-memory only — never persisted to QSettings
        return self._rustfs_secret

    @rustfs_secret_key.setter
    def rustfs_secret_key(self, v: str):
        self._rustfs_secret = v

    @property
    def rustfs_bucket(self) -> str:
        return self._s.value("rustfs/bucket", "photos", str)

    @rustfs_bucket.setter
    def rustfs_bucket(self, v: str):
        self._s.setValue("rustfs/bucket", v)

    # ── CompreFace ────────────────────────────────────────────────────────────
    @property
    def compreface_url(self) -> str:
        return self._s.value("compreface/url", "", str)

    @compreface_url.setter
    def compreface_url(self, v: str):
        self._s.setValue("compreface/url", v)

    @property
    def compreface_api_key(self) -> str:
        # Stored in-memory only
        return self._cf_api_key

    @compreface_api_key.setter
    def compreface_api_key(self, v: str):
        self._cf_api_key = v

    @property
    def similarity_threshold(self) -> float:
        return float(self._s.value("compreface/similarity_threshold", 0.85))

    @similarity_threshold.setter
    def similarity_threshold(self, v: float):
        self._s.setValue("compreface/similarity_threshold", v)

    # ── Face DB ───────────────────────────────────────────────────────────────
    @property
    def face_db_path(self) -> str:
        import os
        default = os.path.join(os.path.expanduser("~"), "RaidCloud", "faces.db")
        return self._s.value("facedb/path", default, str)

    @face_db_path.setter
    def face_db_path(self, v: str):
        self._s.setValue("facedb/path", v)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def sync(self):
        """Force flush to disk."""
        self._s.sync()

    def reset(self):
        """Clear all stored settings."""
        self._s.clear()
        self._s.sync()
