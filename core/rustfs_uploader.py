"""
core/rustfs_uploader.py — S3-compatible uploader for RustFS running on Unraid.

Uses boto3 with a custom endpoint_url.  Works with any S3-compatible store
(RustFS, MinIO, Ceph, Wasabi, etc.).  Call from a QThread worker only.
"""

import os
from typing import Optional, Callable


class RustFSError(Exception):
    """Raised when a RustFS / S3 operation fails."""


class RustFSUploader:
    """
    Synchronous S3-compatible uploader.

    Each instance holds a boto3 S3 client pointed at your RustFS endpoint.
    Create one per QThread run; boto3 clients are not thread-safe when shared.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RustFSError(
                "boto3 is not installed. Run: pip install boto3"
            ) from exc

        self.bucket = bucket
        self._endpoint = endpoint.rstrip("/")

        self._s3 = boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=120,
                retries={"max_attempts": 3},
            ),
        )

    # ── Connectivity ──────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """
        Verify endpoint, credentials, and bucket access.
        Attempts to create the bucket if it doesn't exist yet.
        """
        try:
            self._s3.head_bucket(Bucket=self.bucket)
            return True, f"Connected ✓  (bucket: '{self.bucket}')"
        except Exception as exc:
            code = ""
            resp = getattr(exc, "response", None)
            if resp:
                code = resp.get("Error", {}).get("Code", "")

            if code in ("404", "NoSuchBucket"):
                try:
                    self._s3.create_bucket(Bucket=self.bucket)
                    return True, f"Bucket '{self.bucket}' created ✓"
                except Exception as ce:
                    return False, f"Bucket not found and creation failed: {ce}"

            return False, f"RustFS connection error: {exc}"

    # ── Album folder ──────────────────────────────────────────────────────────

    def ensure_prefix(self, album_name: str) -> None:
        """
        Create a zero-byte folder marker so the album appears as a folder
        in the RustFS / S3 UI.  Idempotent — safe to call multiple times.
        """
        key = f"{album_name}/"
        try:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=b"")
        except Exception as exc:
            raise RustFSError(
                f"Failed to create album prefix '{key}': {exc}"
            ) from exc

    # ── File upload ───────────────────────────────────────────────────────────

    def upload_file(
        self,
        local_path: str,
        album_name: str,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> str:
        """
        Upload a local file to  <bucket>/<album_name>/<filename>.

        Args:
            local_path:        Absolute path to the source file.
            album_name:        Destination album / S3 prefix.
            filename:          Override filename; defaults to basename of local_path.
            progress_callback: Called with bytes_transferred as the upload progresses.

        Returns:
            The full S3 key (e.g. "Wedding 2025/photo_001.jpg").

        Raises:
            RustFSError on failure.
        """
        if filename is None:
            filename = os.path.basename(local_path)

        key = f"{album_name}/{filename}"

        try:
            if progress_callback:
                self._s3.upload_file(
                    local_path,
                    self.bucket,
                    key,
                    Callback=progress_callback,
                )
            else:
                self._s3.upload_file(local_path, self.bucket, key)
        except Exception as exc:
            raise RustFSError(
                f"Upload failed for '{filename}': {exc}"
            ) from exc

        return key

    def get_presigned_url(self, key: str, expiry_seconds: int = 86400) -> str:
        """
        Generate a pre-signed GET URL for an uploaded object.

        Returns:
            A time-limited URL string.
        """
        try:
            return self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiry_seconds,
            )
        except Exception as exc:
            raise RustFSError(
                f"Could not generate pre-signed URL for '{key}': {exc}"
            ) from exc
