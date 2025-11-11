"""Tests for cloud folder connectors."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem
from relay_ai.connectors.cloud.gdrive import GDriveConnector
from relay_ai.connectors.cloud.onedrive import OneDriveConnector
from relay_ai.connectors.cloud.s3 import S3Connector


def test_connector_config_defaults():
    """Connector config has sensible defaults."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="gdrive")

    assert config.tenant_id == "tenant1"
    assert config.connector_name == "gdrive"
    assert config.include_patterns == ["*"]
    assert config.exclude_patterns == []
    assert config.mime_types == []


def test_connector_config_with_filters():
    """Connector config supports filters."""
    config = ConnectorConfig(
        tenant_id="tenant1",
        connector_name="gdrive",
        include_patterns=["*.pdf", "*.docx"],
        exclude_patterns=["*/Archive/*"],
        mime_types=["application/pdf"],
        max_size_bytes=10_000_000,
    )

    assert len(config.include_patterns) == 2
    assert len(config.exclude_patterns) == 1
    assert config.max_size_bytes == 10_000_000


def test_glob_pattern_matching():
    """Glob pattern matching works correctly."""
    config = ConnectorConfig(
        tenant_id="tenant1", connector_name="test", include_patterns=["*.pdf"], exclude_patterns=["*/Archive/*"]
    )

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector._matches_glob = CloudConnector._matches_glob.__get__(connector)

    # Test include patterns
    assert connector._matches_glob("/path/to/file.pdf", "*.pdf")
    assert not connector._matches_glob("/path/to/file.txt", "*.pdf")

    # Test exclude patterns
    assert connector._matches_glob("/path/Archive/file.pdf", "*/Archive/*")
    assert not connector._matches_glob("/path/Active/file.pdf", "*/Archive/*")


def test_filter_by_size():
    """Filter items by size limit."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="test", max_size_bytes=1000)

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector.should_include = CloudConnector.should_include.__get__(connector)

    # Small file - should include
    small_item = StagedItem(
        external_id="1",
        path="/file.txt",
        name="file.txt",
        mime_type="text/plain",
        size_bytes=500,
        last_modified=datetime.now(timezone.utc),
    )
    assert connector.should_include(small_item)

    # Large file - should exclude
    large_item = StagedItem(
        external_id="2",
        path="/large.txt",
        name="large.txt",
        mime_type="text/plain",
        size_bytes=2000,
        last_modified=datetime.now(timezone.utc),
    )
    assert not connector.should_include(large_item)


def test_filter_by_mime_type():
    """Filter items by MIME type."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="test", mime_types=["application/pdf"])

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector.should_include = CloudConnector.should_include.__get__(connector)

    # PDF - should include
    pdf_item = StagedItem(
        external_id="1",
        path="/doc.pdf",
        name="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1000,
        last_modified=datetime.now(timezone.utc),
    )
    assert connector.should_include(pdf_item)

    # TXT - should exclude
    txt_item = StagedItem(
        external_id="2",
        path="/doc.txt",
        name="doc.txt",
        mime_type="text/plain",
        size_bytes=1000,
        last_modified=datetime.now(timezone.utc),
    )
    assert not connector.should_include(txt_item)


def test_filter_excludes_folders():
    """Folders are always excluded."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="test")

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector.should_include = CloudConnector.should_include.__get__(connector)

    folder_item = StagedItem(
        external_id="1",
        path="/folder",
        name="folder",
        mime_type="folder",
        size_bytes=0,
        last_modified=datetime.now(timezone.utc),
        is_folder=True,
    )

    assert not connector.should_include(folder_item)


def test_filter_items_batch():
    """Filter multiple items at once."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="test", include_patterns=["*.pdf"])

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector.should_include = CloudConnector.should_include.__get__(connector)
    connector.filter_items = CloudConnector.filter_items.__get__(connector)
    connector._matches_glob = CloudConnector._matches_glob.__get__(connector)

    items = [
        StagedItem(
            external_id="1",
            path="/doc.pdf",
            name="doc.pdf",
            mime_type="application/pdf",
            size_bytes=1000,
            last_modified=datetime.now(timezone.utc),
        ),
        StagedItem(
            external_id="2",
            path="/doc.txt",
            name="doc.txt",
            mime_type="text/plain",
            size_bytes=1000,
            last_modified=datetime.now(timezone.utc),
        ),
        StagedItem(
            external_id="3",
            path="/report.pdf",
            name="report.pdf",
            mime_type="application/pdf",
            size_bytes=2000,
            last_modified=datetime.now(timezone.utc),
        ),
    ]

    filtered = connector.filter_items(items)

    assert len(filtered) == 2  # Only PDFs
    assert all(item.mime_type == "application/pdf" for item in filtered)


def test_gdrive_authentication_service_account():
    """GDrive authentication requires env vars."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="gdrive")
    connector = GDriveConnector(config)

    # Without env vars, authentication should fail
    result = connector.authenticate()
    assert result is False


def test_onedrive_list_items():
    """OneDrive lists items correctly."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="onedrive")
    connector = OneDriveConnector(config)
    connector.access_token = "fake-token"

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "item1",
                    "name": "file.pdf",
                    "size": 1234,
                    "lastModifiedDateTime": "2025-10-01T12:00:00Z",
                    "file": {"mimeType": "application/pdf"},
                }
            ],
            "@odata.nextLink": None,
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        items, next_token = connector.list_items()

        assert len(items) == 1
        assert items[0].name == "file.pdf"
        assert items[0].external_id == "item1"
        assert next_token is None


def test_s3_list_items():
    """S3 lists objects correctly."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="s3")
    connector = S3Connector(config, bucket_name="test-bucket")

    # Mock S3 client directly
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "folder/file.pdf",
                "Size": 1234,
                "LastModified": datetime.now(timezone.utc),
                "ETag": '"abc123"',
                "StorageClass": "STANDARD",
            }
        ],
        "NextContinuationToken": None,
    }
    connector.s3_client = mock_s3

    items, next_token = connector.list_items()

    assert len(items) == 1
    assert items[0].name == "file.pdf"
    assert items[0].path == "folder/file.pdf"
    assert next_token is None


def test_onedrive_delta_changes():
    """OneDrive delta sync works."""
    config = ConnectorConfig(tenant_id="tenant1", connector_name="onedrive")
    connector = OneDriveConnector(config)
    connector.access_token = "fake-token"

    with patch("requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "item1",
                    "name": "updated-file.pdf",
                    "size": 5678,
                    "lastModifiedDateTime": "2025-10-01T14:00:00Z",
                    "file": {"mimeType": "application/pdf"},
                }
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/delta?token=abc123",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        changes, new_token = connector.get_delta_changes(delta_token="old-token-url")

        assert len(changes) == 1
        assert changes[0].name == "updated-file.pdf"
        assert new_token == "https://graph.microsoft.com/delta?token=abc123"


def test_include_exclude_priority():
    """Exclude patterns take priority over include patterns."""
    config = ConnectorConfig(
        tenant_id="tenant1", connector_name="test", include_patterns=["*.pdf"], exclude_patterns=["*/Archive/*"]
    )

    connector = MagicMock(spec=CloudConnector)
    connector.config = config
    connector.should_include = CloudConnector.should_include.__get__(connector)
    connector._matches_glob = CloudConnector._matches_glob.__get__(connector)

    # PDF in Archive - should exclude
    archived_pdf = StagedItem(
        external_id="1",
        path="/Archive/doc.pdf",
        name="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1000,
        last_modified=datetime.now(timezone.utc),
    )
    assert not connector.should_include(archived_pdf)

    # PDF outside Archive - should include
    active_pdf = StagedItem(
        external_id="2",
        path="/Active/doc.pdf",
        name="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1000,
        last_modified=datetime.now(timezone.utc),
    )
    assert connector.should_include(active_pdf)
