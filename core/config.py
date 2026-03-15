"""
core/config.py — QSettings-based configuration for RaidCloud Immich Suite.
"""

from PySide6.QtCore import QSettings

try:
    import keyring as _keyring
    _KEYRING_SERVICE = "RaidCloud.ImmichSuite"
    _KEYRING_ACCOUNT = "api_key"
    _KEYRING_OK = True
except Exception:
    _KEYRING_OK = False


class AppConfig:
    """Typed wrapper around QSettings for all persistent app settings."""

    ORG  = "RaidCloud"
    APP  = "ImmichSuite"

    def __init__(self):
        self._s = QSettings(self.ORG, self.APP)

    # ── Connection ────────────────────────────────────────────────────────────
    @property
    def server_url(self) -> str:
        return self._s.value("connection/server_url", "https://photos.raidcloud.in", str)

    @server_url.setter
    def server_url(self, v: str):
        self._s.setValue("connection/server_url", v)

    @property
    def api_key(self) -> str:
        if _KEYRING_OK:
            try:
                val = _keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
                if val is not None:
                    # Key already in keychain — use it directly
                    return val
                # Key not yet in keychain — check QSettings for auto-migration
                legacy = self._s.value("connection/api_key", "", str)
                if legacy:
                    _keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, legacy)
                    self._s.remove("connection/api_key")
                    return legacy
                return ""
            except Exception:
                pass
        # Fallback: plaintext QSettings (keyring unavailable)
        return self._s.value("connection/api_key", "", str)

    @api_key.setter
    def api_key(self, v: str):
        if _KEYRING_OK:
            try:
                if v:
                    _keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, v)
                else:
                    try:
                        _keyring.delete_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
                    except Exception:
                        pass
                # Also remove any old plaintext value from QSettings
                self._s.remove("connection/api_key")
                return
            except Exception:
                pass
        # Fallback: plaintext QSettings
        self._s.setValue("connection/api_key", v)

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

    # ── Helpers ───────────────────────────────────────────────────────────────
    def sync(self):
        """Force flush to disk."""
        self._s.sync()

    def reset(self):
        """Clear all stored settings."""
        self._s.clear()
        self._s.sync()
