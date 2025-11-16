"""Cloud folder connectors for GDrive, OneDrive, SharePoint, Dropbox, Box, S3, GCS."""

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem
from relay_ai.connectors.cloud.box import BoxConnector
from relay_ai.connectors.cloud.dropbox import DropboxConnector
from relay_ai.connectors.cloud.gcs import GCSConnector
from relay_ai.connectors.cloud.gdrive import GDriveConnector
from relay_ai.connectors.cloud.onedrive import OneDriveConnector
from relay_ai.connectors.cloud.s3 import S3Connector
from relay_ai.connectors.cloud.sharepoint import SharePointConnector

__all__ = [
    "CloudConnector",
    "StagedItem",
    "ConnectorConfig",
    "GDriveConnector",
    "OneDriveConnector",
    "SharePointConnector",
    "DropboxConnector",
    "BoxConnector",
    "S3Connector",
    "GCSConnector",
]
