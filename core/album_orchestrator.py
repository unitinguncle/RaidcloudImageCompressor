"""
core/album_orchestrator.py — QThread coordinator for Smart Album Upload.

Three-phase pipeline:
  Phase 1 (serial)  : Create Immich album + RustFS prefix folder
  Phase 2 (parallel): Upload each file to Immich + RustFS + CompreFace index
  Phase 3 (serial)  : Bulk-add assets to album → create shared link / share
"""

import os
import hashlib
import concurrent.futures
from typing import Optional

from PySide6.QtCore import QThread, Signal

from core.immich_api     import ImmichApi, ImmichApiError
from core.rustfs_uploader import RustFSUploader, RustFSError
from core.compreface_client import ComprefaceClient
from core.face_db        import FaceDB

_UNKNOWN_PREFIX = "unknown"


class AlbumOrchestrator(QThread):
    """
    Orchestrates the full Smart Album upload flow.

    Signals
    -------
    phase_changed(str)          human-readable phase label
    progress(int)               0-100 overall completion
    file_done(filename, status) per-file result string
    album_created(id, name)     fired after Immich album is created / confirmed
    shared_link_ready(url)      fired after a public link is generated
    log(message, is_error)      log line for the UI text area
    finished()                  all phases done (or cancelled / errored)
    """

    phase_changed     = Signal(str)
    progress          = Signal(int)
    file_done         = Signal(str, str)
    album_created     = Signal(str, str)
    shared_link_ready = Signal(str)
    log               = Signal(str, bool)
    finished          = Signal()

    def __init__(
        self,
        files: list[str],
        album_name: str,
        # ── Immich ──────────────────────
        immich_url: str,
        immich_key: str,
        use_immich: bool = True,
        existing_album_id: Optional[str] = None,
        sharing_mode: str = "link",       # "link" | "users" | "none"
        share_user_ids: Optional[list[str]] = None,
        # ── RustFS ──────────────────────
        rustfs_endpoint: str = "",
        rustfs_access_key: str = "",
        rustfs_secret_key: str = "",
        rustfs_bucket: str = "",
        use_rustfs: bool = True,
        # ── CompreFace ──────────────────
        compreface_url: str = "",
        compreface_api_key: str = "",
        use_compreface: bool = True,
        sim_threshold: float = 0.85,
        # ── Local DB ────────────────────
        face_db: Optional[FaceDB] = None,
        parent=None,
    ):
        super().__init__(parent)

        self.files              = list(files)
        self.album_name         = album_name
        self.use_immich         = use_immich
        self.immich_url         = immich_url
        self.immich_key         = immich_key
        self.existing_album_id  = existing_album_id or ""
        self.sharing_mode       = sharing_mode
        self.share_user_ids     = share_user_ids or []
        self.use_rustfs         = use_rustfs
        self.rustfs_endpoint    = rustfs_endpoint
        self.rustfs_access_key  = rustfs_access_key
        self.rustfs_secret_key  = rustfs_secret_key
        self.rustfs_bucket      = rustfs_bucket
        self.use_compreface     = use_compreface
        self.compreface_url     = compreface_url
        self.compreface_api_key = compreface_api_key
        self.sim_threshold      = sim_threshold
        self.face_db            = face_db

        self._cancel    = False
        self._asset_ids: list[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def cancel(self) -> None:
        self._cancel = True

    # ── Main flow ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        total = len(self.files)
        if total == 0:
            self.log.emit("No files selected.", False)
            self.finished.emit()
            return

        # Phase 1
        try:
            album_id = self._phase1()
        except Exception as exc:
            self.log.emit(f"[ERROR] Album setup failed: {exc}", True)
            self.finished.emit()
            return

        if self._cancel:
            self.log.emit("Cancelled before upload started.", False)
            self.finished.emit()
            return

        # Phase 2
        self._phase2(album_id, total)

        if self._cancel:
            self.log.emit("Cancelled after upload.", False)
            self.finished.emit()
            return

        # Phase 3
        self._phase3(album_id)

        self.finished.emit()

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def _phase1(self) -> str:
        self.phase_changed.emit("🎞  Creating Album")
        self.log.emit(f"Phase 1: Setting up album '{self.album_name}'…", False)

        album_id = self.existing_album_id

        if self.use_immich:
            api = ImmichApi(self.immich_url, self.immich_key)
            if not album_id:
                album_id = api.create_album(self.album_name)
                self.log.emit(f"✓ Immich album created  (id: {album_id[:8]}…)", False)
            else:
                self.log.emit(f"✓ Using existing Immich album  (id: {album_id[:8]}…)", False)
            self.album_created.emit(album_id, self.album_name)

        if self.use_rustfs and self.rustfs_endpoint:
            rustfs = self._make_rustfs()
            rustfs.ensure_prefix(self.album_name)
            self.log.emit(f"✓ RustFS prefix '{self.album_name}/' ready", False)

        return album_id

    # ── Phase 2 ───────────────────────────────────────────────────────────────

    def _phase2(self, album_id: str, total: int) -> None:
        self.phase_changed.emit("⬆  Uploading Files")
        self.log.emit(f"Phase 2: Processing {total} file(s) in parallel…", False)

        # Build per-thread clients (not shared across threads)
        immich_api = ImmichApi(self.immich_url, self.immich_key) if self.use_immich else None
        rustfs     = self._make_rustfs() if (self.use_rustfs and self.rustfs_endpoint) else None
        cf_client  = (
            ComprefaceClient(
                self.compreface_url,
                self.compreface_api_key,
                sim_threshold=self.sim_threshold,
            )
            if (self.use_compreface and self.compreface_url)
            else None
        )

        max_workers = min(6, os.cpu_count() or 4)
        completed   = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
            futures = {
                exe.submit(
                    self._process_file,
                    fp, album_id, immich_api, rustfs, cf_client,
                ): fp
                for fp in self.files
            }

            for fut in concurrent.futures.as_completed(futures):
                if self._cancel:
                    self.log.emit("Upload cancelled by user.", False)
                    exe.shutdown(wait=False, cancel_futures=True)
                    break

                fp    = futures[fut]
                fname = os.path.basename(fp)
                try:
                    status = fut.result()
                    self.file_done.emit(fname, status)
                except Exception as exc:
                    self.file_done.emit(fname, "FAILED")
                    self.log.emit(f"[ERROR] {fname}: {exc}", True)

                completed += 1
                self.progress.emit(int(completed / total * 100))

    def _process_file(
        self,
        file_path: str,
        album_id: str,
        immich_api: Optional[ImmichApi],
        rustfs: Optional[RustFSUploader],
        cf_client: Optional[ComprefaceClient],
    ) -> str:
        """Worker: push one file to all enabled destinations. Returns status string."""
        filename   = os.path.basename(file_path)
        asset_id   = ""
        s3_key     = ""
        subject    = None
        similarity: Optional[float] = None
        parts: list[str] = []

        # ── Immich upload
        if immich_api:
            try:
                asset_id = immich_api.upload_asset(file_path)
                if asset_id:
                    self._asset_ids.append(asset_id)
                    parts.append("Immich ✓")
                else:
                    parts.append("Immich (dup)")
            except ImmichApiError as e:
                parts.append(f"Immich ✗")
                self.log.emit(f"[WARN] Immich upload {filename}: {e}", True)

        # ── RustFS upload
        if rustfs:
            try:
                s3_key = rustfs.upload_file(file_path, self.album_name, filename)
                parts.append("RustFS ✓")
            except RustFSError as e:
                parts.append("RustFS ✗")
                self.log.emit(f"[WARN] RustFS upload {filename}: {e}", True)

        # ── CompreFace recognition / indexing
        if cf_client:
            try:
                match = cf_client.best_match(file_path)
                if match:
                    subject, similarity = match
                    parts.append(f"👤 {subject} ({similarity:.0%})")
                else:
                    # No matchabove threshold — store as stable unknown ID
                    h = hashlib.md5(filename.encode()).hexdigest()[:6]
                    subject = f"{_UNKNOWN_PREFIX}_{h}"
                    parts.append("👤 unknown")
            except Exception as e:
                parts.append("Face ✗")
                self.log.emit(f"[WARN] CompreFace {filename}: {e}", True)

        # ── Persist to local face DB
        if self.face_db and asset_id:
            try:
                self.face_db.insert_record(
                    album_name=self.album_name,
                    asset_id=asset_id,
                    filename=filename,
                    subject=subject,
                    similarity=similarity,
                    s3_key=s3_key,
                )
            except Exception:
                pass  # DB errors should never block the upload pipeline

        return " │ ".join(parts) if parts else "skipped"

    # ── Phase 3 ───────────────────────────────────────────────────────────────

    def _phase3(self, album_id: str) -> None:
        self.phase_changed.emit("🔗  Finalising")
        self.log.emit("Phase 3: Adding assets to album & sharing…", False)

        if not (self.use_immich and album_id):
            self.phase_changed.emit("✅  Complete")
            return

        api = ImmichApi(self.immich_url, self.immich_key)

        # Bulk-add all collected asset IDs
        if self._asset_ids:
            try:
                api.add_assets_to_album(album_id, self._asset_ids)
                self.log.emit(
                    f"✓ {len(self._asset_ids)} asset(s) added to Immich album", False
                )
            except Exception as exc:
                self.log.emit(f"[WARN] add_assets_to_album: {exc}", True)

        # Sharing
        if self.sharing_mode == "link":
            try:
                link = api.create_shared_link(album_id)
                self.log.emit(f"✓ Shared link created: {link}", False)
                self.shared_link_ready.emit(link)
            except Exception as exc:
                self.log.emit(f"[WARN] create_shared_link: {exc}", True)

        elif self.sharing_mode == "users" and self.share_user_ids:
            try:
                api.share_album_with_users(album_id, self.share_user_ids)
                self.log.emit(
                    f"✓ Album shared with {len(self.share_user_ids)} user(s)", False
                )
            except Exception as exc:
                self.log.emit(f"[WARN] share_with_users: {exc}", True)

        self.phase_changed.emit("✅  Complete")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_rustfs(self) -> RustFSUploader:
        return RustFSUploader(
            endpoint=self.rustfs_endpoint,
            access_key=self.rustfs_access_key,
            secret_key=self.rustfs_secret_key,
            bucket=self.rustfs_bucket,
        )
