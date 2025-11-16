"""SharePoint connector with delta sync support."""

import os
from datetime import datetime
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class SharePointConnector(CloudConnector):
    """
    SharePoint connector using Microsoft Graph API.

    Requires:
    - SHAREPOINT_CLIENT_ID
    - SHAREPOINT_CLIENT_SECRET
    - SHAREPOINT_TENANT_ID
    - SHAREPOINT_SITE_ID (or SHAREPOINT_SITE_URL)
    - SHAREPOINT_ACCESS_TOKEN

    Scopes: Sites.Read.All, Files.Read.All

    Delta sync via /sites/{site-id}/drive/root/delta endpoint.
    """

    def __init__(self, config: ConnectorConfig, site_id: Optional[str] = None):
        super().__init__(config)
        self.access_token: Optional[str] = None
        self.site_id = site_id or os.getenv("SHAREPOINT_SITE_ID")
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"

    def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API."""
        try:
            self.access_token = os.getenv("SHAREPOINT_ACCESS_TOKEN")
            if self.access_token:
                return True

            # TODO: Implement OAuth flow (same as OneDrive)
            client_id = os.getenv("SHAREPOINT_CLIENT_ID")
            client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET")
            tenant_id = os.getenv("SHAREPOINT_TENANT_ID")

            if client_id and client_secret and tenant_id:
                print("SharePoint OAuth flow not fully implemented. Set SHAREPOINT_ACCESS_TOKEN.")
                return False

            return False

        except Exception as e:
            print(f"SharePoint authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List items in SharePoint document library."""
        if not self.access_token or not self.site_id:
            if not self.authenticate():
                return [], None

        try:
            import requests

            # Build URL for site drive
            if folder_id:
                url = f"{self.graph_endpoint}/sites/{self.site_id}/drive/items/{folder_id}/children"
            else:
                url = f"{self.graph_endpoint}/sites/{self.site_id}/drive/root/children"

            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"$top": 100}
            if page_token:
                url = page_token  # Full URL

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
            print(f"SharePoint list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """Get incremental changes using SharePoint delta API."""
        if not self.access_token or not self.site_id:
            if not self.authenticate():
                return [], None

        try:
            import requests

            if delta_token:
                url = delta_token
            else:
                url = f"{self.graph_endpoint}/sites/{self.site_id}/drive/root/delta"

            headers = {"Authorization": f"Bearer {self.access_token}"}
            items = []

            while url:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                for item in data.get("value", []):
                    if not item.get("deleted"):
                        staged_item = self._item_to_staged_item(item)
                        items.append(staged_item)

                url = data.get("@odata.nextLink")
                if not url:
                    delta_link = data.get("@odata.deltaLink")
                    return items, delta_link

            return items, delta_token

        except Exception as e:
            print(f"SharePoint get_delta_changes failed: {e}")
            return [], delta_token

    def _item_to_staged_item(self, item: dict[str, Any]) -> StagedItem:
        """Convert Graph API item to StagedItem."""
        is_folder = "folder" in item
        size = item.get("size", 0)
        modified_time = datetime.fromisoformat(item.get("lastModifiedDateTime").replace("Z", "+00:00"))

        path = item.get("name")
        parent_ref = item.get("parentReference", {})
        parent_path = parent_ref.get("path", "")
        if parent_path and "/drive/root:" in parent_path:
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
            metadata={"sharepoint_item_id": item.get("id"), "web_url": item.get("webUrl"), "site_id": self.site_id},
        )
