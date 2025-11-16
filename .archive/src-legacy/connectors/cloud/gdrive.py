"""Google Drive connector with delta sync support."""

import os
from datetime import datetime
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class GDriveConnector(CloudConnector):
    """
    Google Drive connector using Drive API v3.

    Requires:
    - GDRIVE_CREDENTIALS_JSON or GDRIVE_SERVICE_ACCOUNT_JSON
    - Scopes: https://www.googleapis.com/auth/drive.readonly

    Delta sync via Drive Changes API.
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.service = None
        self.start_page_token: Optional[str] = None

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API."""
        try:
            # Try service account first
            service_account_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON")
            if service_account_json:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build

                credentials = service_account.Credentials.from_service_account_file(
                    service_account_json, scopes=["https://www.googleapis.com/auth/drive.readonly"]
                )
                self.service = build("drive", "v3", credentials=credentials)
                return True

            # Fallback to OAuth credentials
            credentials_json = os.getenv("GDRIVE_CREDENTIALS_JSON")
            if credentials_json:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build

                # In production, implement OAuth flow with token refresh
                # For now, assume credentials JSON contains refresh token
                self.service = build("drive", "v3", credentials=Credentials.from_authorized_user_file(credentials_json))
                return True

            # No credentials found
            return False

        except Exception as e:
            print(f"GDrive authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List items in a Google Drive folder."""
        if not self.service:
            if not self.authenticate():
                return [], None

        try:
            query = "trashed = false"
            if folder_id:
                query += f" and '{folder_id}' in parents"

            results = (
                self.service.files()
                .list(
                    q=query,
                    pageSize=100,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)",
                )
                .execute()
            )

            items = []
            for file in results.get("files", []):
                item = self._file_to_staged_item(file)
                items.append(item)

            next_page_token = results.get("nextPageToken")
            return items, next_page_token

        except Exception as e:
            print(f"GDrive list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """Get incremental changes using Drive Changes API."""
        if not self.service:
            if not self.authenticate():
                return [], None

        try:
            # Get start page token if not provided
            if not delta_token:
                response = self.service.changes().getStartPageToken().execute()
                delta_token = response.get("startPageToken")

            # Fetch changes
            changes = []
            page_token = delta_token

            while page_token:
                response = (
                    self.service.changes()
                    .list(
                        pageToken=page_token,
                        pageSize=100,
                        fields="nextPageToken, newStartPageToken, changes(fileId, file(id, name, mimeType, size, modifiedTime, parents, trashed))",
                    )
                    .execute()
                )

                for change in response.get("changes", []):
                    file = change.get("file")
                    if file and not file.get("trashed", False):
                        items = self._file_to_staged_item(file)
                        changes.append(items)

                page_token = response.get("nextPageToken")
                new_start_token = response.get("newStartPageToken")

                if new_start_token:
                    # End of changes
                    return changes, new_start_token

            return changes, delta_token

        except Exception as e:
            print(f"GDrive get_delta_changes failed: {e}")
            return [], delta_token

    def _file_to_staged_item(self, file: dict[str, Any]) -> StagedItem:
        """Convert Drive API file to StagedItem."""
        is_folder = file.get("mimeType") == "application/vnd.google-apps.folder"
        size = int(file.get("size", 0)) if not is_folder else 0
        modified_time = datetime.fromisoformat(file.get("modifiedTime").replace("Z", "+00:00"))

        return StagedItem(
            external_id=file.get("id"),
            path=file.get("name"),  # Simplified; full path requires parent traversal
            name=file.get("name"),
            mime_type=file.get("mimeType"),
            size_bytes=size,
            last_modified=modified_time,
            is_folder=is_folder,
            parent_id=file.get("parents", [None])[0] if file.get("parents") else None,
            metadata={"drive_file_id": file.get("id")},
        )
