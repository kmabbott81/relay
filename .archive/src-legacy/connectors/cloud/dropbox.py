"""Dropbox connector with webhook-based delta sync support."""

import os
from datetime import datetime
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class DropboxConnector(CloudConnector):
    """
    Dropbox connector using Dropbox API v2.

    Requires:
    - DROPBOX_ACCESS_TOKEN (OAuth2 token)
    - DROPBOX_APP_KEY, DROPBOX_APP_SECRET (for OAuth flow)

    Scopes: files.metadata.read, files.content.read

    Delta sync via /files/list_folder/continue and cursor-based pagination.
    Webhooks via /files/list_folder/longpoll for push notifications.
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.access_token: Optional[str] = None
        self.api_endpoint = "https://api.dropboxapi.com/2"

    def authenticate(self) -> bool:
        """Authenticate with Dropbox API."""
        try:
            self.access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
            if self.access_token:
                return True

            # TODO: Implement OAuth flow
            app_key = os.getenv("DROPBOX_APP_KEY")
            app_secret = os.getenv("DROPBOX_APP_SECRET")

            if app_key and app_secret:
                print("Dropbox OAuth flow not fully implemented. Set DROPBOX_ACCESS_TOKEN.")
                return False

            return False

        except Exception as e:
            print(f"Dropbox authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List items in Dropbox folder."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            folder_path = folder_id or ""  # Dropbox uses path-based addressing

            if page_token:
                # Continue from cursor
                url = f"{self.api_endpoint}/files/list_folder/continue"
                payload = {"cursor": page_token}
            else:
                # Start new listing
                url = f"{self.api_endpoint}/files/list_folder"
                payload = {"path": folder_path, "recursive": False, "include_deleted": False, "limit": 100}

            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            items = []
            for entry in data.get("entries", []):
                staged_item = self._entry_to_staged_item(entry)
                items.append(staged_item)

            cursor = data.get("cursor") if data.get("has_more") else None
            return items, cursor

        except Exception as e:
            print(f"Dropbox list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """Get incremental changes using Dropbox cursor-based delta."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            if delta_token:
                # Continue from cursor
                url = f"{self.api_endpoint}/files/list_folder/continue"
                payload = {"cursor": delta_token}
            else:
                # Get initial cursor for root
                url = f"{self.api_endpoint}/files/list_folder"
                payload = {"path": "", "recursive": True, "include_deleted": False}

            headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

            items = []
            cursor = delta_token

            while True:
                response = requests.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                for entry in data.get("entries", []):
                    staged_item = self._entry_to_staged_item(entry)
                    items.append(staged_item)

                cursor = data.get("cursor")
                if not data.get("has_more"):
                    break

                # Prepare for next iteration
                url = f"{self.api_endpoint}/files/list_folder/continue"
                payload = {"cursor": cursor}

            return items, cursor

        except Exception as e:
            print(f"Dropbox get_delta_changes failed: {e}")
            return [], delta_token

    def _entry_to_staged_item(self, entry: dict[str, Any]) -> StagedItem:
        """Convert Dropbox entry to StagedItem."""
        tag = entry.get(".tag")
        is_folder = tag == "folder"

        size = entry.get("size", 0) if not is_folder else 0
        modified_str = entry.get("client_modified") or entry.get("server_modified")
        modified_time = datetime.fromisoformat(modified_str.replace("Z", "+00:00")) if modified_str else datetime.now()

        return StagedItem(
            external_id=entry.get("id"),
            path=entry.get("path_display", entry.get("path_lower")),
            name=entry.get("name"),
            mime_type=self._guess_mime_type(entry.get("name")) if not is_folder else "folder",
            size_bytes=size,
            last_modified=modified_time,
            is_folder=is_folder,
            parent_id=None,  # Dropbox doesn't provide parent_id directly
            metadata={"dropbox_id": entry.get("id"), "rev": entry.get("rev")},
        )

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename extension."""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
