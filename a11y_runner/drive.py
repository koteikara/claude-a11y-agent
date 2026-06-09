# -*- coding: utf-8 -*-
"""Drive storage adapters for input HTML and generated outputs."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveStore:
    def read_text(self, folder_id: str, path_or_id: str) -> str: ...
    def write_text(self, folder_id: str, path: str, content: str) -> str: ...


@dataclass
class InMemoryDriveStore:
    files: dict[tuple[str, str], str]
    links: dict[tuple[str, str], str] | None = None

    def __post_init__(self) -> None:
        if self.links is None:
            self.links = {}

    def read_text(self, folder_id: str, path_or_id: str) -> str:
        return self.files[(folder_id, path_or_id)]

    def write_text(self, folder_id: str, path: str, content: str) -> str:
        self.files[(folder_id, path)] = content
        link = f"drive://{folder_id}/{path}"
        self.links[(folder_id, path)] = link
        return link


class GoogleDriveStore:
    """Google Drive adapter using google-api-python-client."""

    def __init__(self):
        missing = [
            name for name in ("google.auth", "googleapiclient.discovery", "googleapiclient.http")
            if not _has_module(name)
        ]
        if missing:  # pragma: no cover - depends on optional package
            raise RuntimeError(
                "google-api-python-client and google-auth are required. Install runner dependencies with "
                "`pip install -r requirements-runner.txt`."
            )
        import google.auth
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

        credentials, _ = google.auth.default(scopes=DRIVE_SCOPES)
        self._build = build
        self._download_cls = MediaIoBaseDownload
        self._upload_cls = MediaIoBaseUpload
        self._service = build("drive", "v3", credentials=credentials)

    def read_text(self, folder_id: str, path_or_id: str) -> str:
        import io

        file_id = path_or_id if self._looks_like_drive_id(path_or_id) else self._find_file_id(folder_id, path_or_id)
        request = self._service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = self._download_cls(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue().decode("utf-8", errors="replace")

    def write_text(self, folder_id: str, path: str, content: str) -> str:
        import io

        name = path.split("/")[-1]
        parent_id = self._ensure_folder_path(folder_id, path.split("/")[:-1])
        body = {"name": name, "parents": [parent_id], "mimeType": "text/html"}
        media = self._upload_cls(io.BytesIO(content.encode("utf-8")), mimetype="text/html", resumable=False)
        existing = self._find_file_id(parent_id, name, missing_ok=True)
        if existing:
            file_obj = self._service.files().update(fileId=existing, media_body=media, fields="id,webViewLink").execute()
        else:
            file_obj = self._service.files().create(body=body, media_body=media, fields="id,webViewLink").execute()
        return file_obj.get("webViewLink", f"https://drive.google.com/file/d/{file_obj['id']}/view")

    def _find_file_id(self, parent_id: str, name_or_path: str, *, missing_ok: bool = False) -> str | None:
        current_parent = parent_id
        parts = [part for part in name_or_path.split("/") if part]
        for index, part in enumerate(parts):
            mime_filter = " and mimeType = 'application/vnd.google-apps.folder'" if index < len(parts) - 1 else ""
            query = (
                f"'{current_parent}' in parents and name = '{part.replace(chr(39), chr(92) + chr(39))}' "
                f"and trashed = false{mime_filter}"
            )
            res = self._service.files().list(q=query, fields="files(id,name)", pageSize=1).execute()
            files = res.get("files", [])
            if not files:
                if missing_ok:
                    return None
                raise FileNotFoundError(name_or_path)
            current_parent = files[0]["id"]
        return current_parent

    def _ensure_folder_path(self, root_folder_id: str, parts: list[str]) -> str:
        parent_id = root_folder_id
        for part in parts:
            found = self._find_file_id(parent_id, part, missing_ok=True)
            if found:
                parent_id = found
                continue
            body = {"name": part, "parents": [parent_id], "mimeType": "application/vnd.google-apps.folder"}
            folder = self._service.files().create(body=body, fields="id").execute()
            parent_id = folder["id"]
        return parent_id

    @staticmethod
    def _looks_like_drive_id(value: str) -> bool:
        return "/" not in value and "." not in value and len(value) >= 20


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False
