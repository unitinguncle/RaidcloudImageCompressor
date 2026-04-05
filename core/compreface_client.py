"""
core/compreface_client.py — CompreFace face recognition REST client.

Handles subject management (create / list / rename) and face
recognition / indexing via the CompreFace Recognition Service API.
Call from a QThread worker only — all methods are synchronous.

CompreFace API reference:
  POST /api/v1/recognition/recognize
  POST /api/v1/recognition/subjects/{subject}/examples
  GET  /api/v1/recognition/subjects
  POST /api/v1/recognition/subjects     (create subject)
"""

import os
import requests
from typing import Optional


DEFAULT_DET_THRESHOLD = 0.80   # face detection confidence floor
DEFAULT_SIM_THRESHOLD = 0.85   # recognition similarity floor


class ComprefaceError(Exception):
    """Raised when a CompreFace API call fails."""


class ComprefaceClient:
    """
    Synchronous CompreFace Face Recognition Service client.

    One instance per recognition service (API key).  Create fresh instances
    inside QThread.run() — requests.Session objects are not thread-safe when
    shared across threads.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        det_prob_threshold: float = DEFAULT_DET_THRESHOLD,
        sim_threshold: float = DEFAULT_SIM_THRESHOLD,
        timeout: int = 60,
    ):
        self.base = base_url.rstrip("/")
        self._headers = {"x-api-key": api_key}
        self.det_threshold = det_prob_threshold
        self.sim_threshold = sim_threshold
        self.timeout = timeout

    # ── Connectivity ──────────────────────────────────────────────────────────

    def test_connection(self) -> tuple[bool, str]:
        """Returns (ok, human-readable message)."""
        try:
            subjects = self.list_subjects()
            return (
                True,
                f"Connected ✓  ({len(subjects)} subject(s) indexed)",
            )
        except ComprefaceError as e:
            return False, str(e)
        except requests.exceptions.ConnectionError:
            return False, "Connection refused — check CompreFace URL."
        except requests.exceptions.Timeout:
            return False, "Connection timed out."
        except Exception as e:
            return False, str(e)

    # ── Subjects ──────────────────────────────────────────────────────────────

    def list_subjects(self) -> list[str]:
        """Return all subject names registered in this recognition service."""
        r = requests.get(
            f"{self.base}/api/v1/recognition/subjects",
            headers=self._headers,
            timeout=self.timeout,
        )
        self._raise(r)
        return r.json().get("subjects", [])

    def ensure_subject(self, subject: str) -> str:
        """
        Create a subject if it doesn't already exist.
        Returns the subject name (unchanged).
        HTTP 400 from CompreFace means "already exists" — treated as success.
        """
        r = requests.post(
            f"{self.base}/api/v1/recognition/subjects",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"subject": subject},
            timeout=self.timeout,
        )
        # 400 = already exists → fine
        if r.status_code not in (200, 201, 400):
            self._raise(r)
        return subject

    def add_subject_example(self, subject: str, image_path: str) -> str:
        """
        Index an image as a known example of *subject*.

        The image should contain exactly one clearly visible face.
        Returns the CompreFace example UUID, or "" on a silent failure.
        """
        self.ensure_subject(subject)
        filename = os.path.basename(image_path)
        with open(image_path, "rb") as fh:
            r = requests.post(
                f"{self.base}/api/v1/recognition/subjects/{subject}/examples",
                headers=self._headers,
                files={"file": (filename, fh, "image/jpeg")},
                params={"det_prob_threshold": self.det_threshold},
                timeout=self.timeout,
            )
        self._raise(r)
        return r.json().get("image_id", "")

    # ── Recognition ───────────────────────────────────────────────────────────

    def recognize(self, image_path: str, limit: int = 3) -> list[dict]:
        """
        Run face recognition on an image file.

        Returns a list of face dicts (one per detected face):
            [{
                "box": {"x_min": …, "y_min": …, "x_max": …, "y_max": …},
                "subjects": [{"subject": "Alice", "similarity": 0.94}, …]
            }]

        Returns [] if no faces are detected OR if the image has no indexed
        matches.  The caller must check subjects[].similarity against
        self.sim_threshold.
        """
        filename = os.path.basename(image_path)
        with open(image_path, "rb") as fh:
            r = requests.post(
                f"{self.base}/api/v1/recognition/recognize",
                headers=self._headers,
                files={"file": (filename, fh, "image/jpeg")},
                params={
                    "det_prob_threshold": self.det_threshold,
                    "prediction_count": limit,
                    "face_plugins": "",
                },
                timeout=self.timeout,
            )

        # 400 = no face detected — not an error condition for our workflow
        if r.status_code == 400:
            return []
        self._raise(r)
        return r.json().get("result", [])

    def best_match(
        self, image_path: str
    ) -> Optional[tuple[str, float]]:
        """
        Convenience wrapper: find the single best subject match in the image.

        Returns:
            (subject_name, similarity_float) if a match above self.sim_threshold
            is found, otherwise None.
        """
        try:
            results = self.recognize(image_path, limit=1)
        except Exception:
            return None

        for face in results:
            subjects = face.get("subjects", [])
            if subjects:
                best = subjects[0]
                sim = float(best.get("similarity", 0))
                if sim >= self.sim_threshold:
                    return best["subject"], sim
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _raise(r: requests.Response) -> None:
        if r.status_code not in (200, 201):
            raise ComprefaceError(
                f"CompreFace HTTP {r.status_code} — {r.text[:200]}"
            )
