"""Box connector with event stream support."""

import os
from datetime import datetime
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class BoxConnector(CloudConnector):
    """
    Box connector using Box API v2.0.

    Requires:
    - BOX_ACCESS_TOKEN (OAuth2 token)
    - BOX_CLIENT_ID, BOX_CLIENT_SECRET (for OAuth flow)

    Scopes: root_readwrite or read_all_files_and_folders

    Delta sync via Box Events API (event stream with stream_position).
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.access_token: Optional[str] = None
        self.api_endpoint = "https://api.box.com/2.0"

    def authenticate(self) -> bool:
        """Authenticate with Box API."""
        try:
            self.access_token = os.getenv("BOX_ACCESS_TOKEN")
            if self.access_token:
                return True

            # TODO: Implement OAuth flow
            client_id = os.getenv("BOX_CLIENT_ID")
            client_secret = os.getenv("BOX_CLIENT_SECRET")

            if client_id and client_secret:
                print("Box OAuth flow not fully implemented. Set BOX_ACCESS_TOKEN.")
                return False

            return False

        except Exception as e:
            print(f"Box authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List items in Box folder."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            folder_id = folder_id or "0"  # 0 = root folder
            url = f"{self.api_endpoint}/folders/{folder_id}/items"

            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"limit": 100, "fields": "id,name,type,size,modified_at,parent"}
            if page_token:
                params["offset"] = page_token

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            items = []
            for entry in data.get("entries", []):
                staged_item = self._entry_to_staged_item(entry)
                items.append(staged_item)

            total_count = data.get("total_count", 0)
            offset = int(page_token or 0)
            limit = params["limit"]
            next_offset = offset + limit if offset + limit < total_count else None

            return items, str(next_offset) if next_offset else None

        except Exception as e:
            print(f"Box list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """Get incremental changes using Box Events API."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            url = f"{self.api_endpoint}/events"
            headers = {"Authorization": f"Bearer {self.access_token}"}

            # Get current stream position if no token
            if not delta_token:
                params = {"stream_type": "changes", "stream_position": "now"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                delta_token = str(data.get("next_stream_position"))
                return [], delta_token  # No events yet, return position for next call

            # Fetch events since stream position
            params = {"stream_type": "changes", "stream_position": delta_token, "limit": 100}
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            items = []
            for event in data.get("entries", []):
                # Filter for file/folder events
                event_type = event.get("event_type")
                if event_type in ["ITEM_CREATE", "ITEM_UPLOAD", "ITEM_MODIFY", "ITEM_MOVE"]:
                    source = event.get("source")
                    if source and source.get("type") in ["file", "folder"]:
                        staged_item = self._entry_to_staged_item(source)
                        items.append(staged_item)

            next_position = str(data.get("next_stream_position"))
            return items, next_position

        except Exception as e:
            print(f"Box get_delta_changes failed: {e}")
            return [], delta_token

    def _entry_to_staged_item(self, entry: dict[str, Any]) -> StagedItem:
        """Convert Box entry to StagedItem."""
        is_folder = entry.get("type") == "folder"
        size = int(entry.get("size", 0)) if not is_folder else 0
        modified_str = entry.get("modified_at")
        modified_time = datetime.fromisoformat(modified_str.replace("Z", "+00:00")) if modified_str else datetime.now()

        # Build path from parent info (simplified)
        name = entry.get("name")
        path = name  # Full path requires parent traversal

        return StagedItem(
            external_id=entry.get("id"),
            path=path,
            name=name,
            mime_type=self._guess_mime_type(name) if not is_folder else "folder",
            size_bytes=size,
            last_modified=modified_time,
            is_folder=is_folder,
            parent_id=entry.get("parent", {}).get("id") if entry.get("parent") else None,
            metadata={"box_id": entry.get("id"), "etag": entry.get("etag")},
        )

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename extension."""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
