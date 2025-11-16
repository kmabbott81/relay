"""OneDrive connector with delta sync support."""

import os
from datetime import datetime
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class OneDriveConnector(CloudConnector):
    """
    OneDrive connector using Microsoft Graph API.

    Requires:
    - ONEDRIVE_CLIENT_ID
    - ONEDRIVE_CLIENT_SECRET
    - ONEDRIVE_TENANT_ID
    - ONEDRIVE_ACCESS_TOKEN (or refresh token for OAuth flow)

    Scopes: Files.Read, Files.Read.All

    Delta sync via /me/drive/root/delta endpoint.
    """

    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self.access_token: Optional[str] = None
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"

    def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API."""
        try:
            # Check if access token already provided
            self.access_token = os.getenv("ONEDRIVE_ACCESS_TOKEN")
            if self.access_token:
                return True

            # TODO: Implement OAuth flow with client credentials or authorization code
            # For production, use MSAL library to get and refresh tokens
            client_id = os.getenv("ONEDRIVE_CLIENT_ID")
            client_secret = os.getenv("ONEDRIVE_CLIENT_SECRET")
            tenant_id = os.getenv("ONEDRIVE_TENANT_ID")

            if client_id and client_secret and tenant_id:
                # Placeholder for token acquisition
                # In production: use msal.ConfidentialClientApplication
                print("OneDrive OAuth flow not fully implemented. Set ONEDRIVE_ACCESS_TOKEN.")
                return False

            return False

        except Exception as e:
            print(f"OneDrive authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List items in OneDrive folder."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            # Build URL
            if folder_id:
                url = f"{self.graph_endpoint}/me/drive/items/{folder_id}/children"
            else:
                url = f"{self.graph_endpoint}/me/drive/root/children"

            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"$top": 100}
            if page_token:
                url = page_token  # Microsoft Graph uses full URL for next page

            response = requests.get(url, headers=headers, params=params if not page_token else {})
            response.raise_for_status()
            data = response.json()

            items = []
            for item in data.get("value", []):
                staged_item = self._item_to_staged_item(item)
                items.append(staged_item)

            next_link = data.get("@odata.nextLink")
            return items, next_link

        except Exception as e:
            print(f"OneDrive list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """Get incremental changes using OneDrive delta API."""
        if not self.access_token:
            if not self.authenticate():
                return [], None

        try:
            import requests

            # Use delta token or start fresh
            if delta_token:
                url = delta_token  # Delta token is a full URL
            else:
                url = f"{self.graph_endpoint}/me/drive/root/delta"

            headers = {"Authorization": f"Bearer {self.access_token}"}
            items = []

            while url:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                for item in data.get("value", []):
                    if not item.get("deleted"):  # Exclude deleted items
                        staged_item = self._item_to_staged_item(item)
                        items.append(staged_item)

                # Check for next link or delta link
                url = data.get("@odata.nextLink")
                if not url:
                    delta_link = data.get("@odata.deltaLink")
                    return items, delta_link

            return items, delta_token

        except Exception as e:
            print(f"OneDrive get_delta_changes failed: {e}")
            return [], delta_token

    def _item_to_staged_item(self, item: dict[str, Any]) -> StagedItem:
        """Convert Graph API item to StagedItem."""
        is_folder = "folder" in item
        size = item.get("size", 0)
        modified_time = datetime.fromisoformat(item.get("lastModifiedDateTime").replace("Z", "+00:00"))

        # Build path from parentReference
        path = item.get("name")
        parent_ref = item.get("parentReference", {})
        parent_path = parent_ref.get("path", "")
        if parent_path:
            # Extract path after /drive/root:
            if "/drive/root:" in parent_path:
                parent_path = parent_path.split("/drive/root:")[1]
                path = f"{parent_path}/{item.get('name')}"

        return StagedItem(
            external_id=item.get("id"),
            path=path,
            name=item.get("name"),
            mime_type=item.get("file", {}).get("mimeType", "application/octet-stream") if not is_folder else "folder",
            size_bytes=size,
            last_modified=modified_time,
            is_folder=is_folder,
            parent_id=parent_ref.get("id"),
            metadata={"onedrive_item_id": item.get("id"), "web_url": item.get("webUrl")},
        )
