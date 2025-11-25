"""
Shared fixtures and test configuration for atlas-mgmt-examples tests.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_modules():
    """
    Reset imported modules between tests to ensure test isolation.
    This prevents module-level state from leaking between tests.
    """
    modules_to_reset = [
        "cleanup_aged_projects_and_clusters",
        "delete_all_clusters_in_organization",
        "delete_empty_projects_in_organization",
        "invite_users_to_organization",
        "pause_all_clusters_in_organization",
        "provision_projects_for_users",
    ]

    # Clean up BEFORE the test - remove modules so they get reimported fresh
    for name in modules_to_reset:
        if name in sys.modules:
            del sys.modules[name]

    yield

    # Clean up AFTER the test as well
    for name in modules_to_reset:
        if name in sys.modules:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def mock_load_dotenv():
    """
    Mock load_dotenv to prevent it from loading real credentials from .env file.
    This ensures tests can control environment variables without interference.
    """
    with patch("dotenv.load_dotenv", return_value=True):
        yield


@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables for Atlas API credentials."""
    env_vars = {
        "ATLAS_PUBLIC_KEY": "test_public_key",
        "ATLAS_PRIVATE_KEY": "test_private_key",
        "ATLAS_ORG_ID": "test_org_id",
        "ATLAS_API_BASE_URL": "https://cloud.mongodb.com/api/atlas/v2",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


@pytest.fixture
def mock_response():
    """Factory fixture to create mock API responses."""

    def _create_response(status_code=200, json_data=None, raise_error=False):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = str(json_data or {})

        if raise_error:
            response.raise_for_status.side_effect = Exception("API Error")
        else:
            response.raise_for_status.return_value = None

        return response

    return _create_response


@pytest.fixture
def sample_projects():
    """Sample list of projects for testing."""
    return [
        {
            "id": "project1",
            "name": "test-project-1",
            "created": "2024-01-01T00:00:00Z",
            "orgId": "test_org_id",
        },
        {
            "id": "project2",
            "name": "test-project-2",
            "created": "2024-06-01T00:00:00Z",
            "orgId": "test_org_id",
        },
    ]


@pytest.fixture
def sample_clusters():
    """Sample list of clusters for testing."""
    return [
        {
            "id": "cluster1",
            "name": "cluster-1",
            "paused": False,
            "stateName": "IDLE",
        },
        {
            "id": "cluster2",
            "name": "cluster-2",
            "paused": True,
            "stateName": "PAUSED",
        },
    ]


@pytest.fixture
def sample_database_users():
    """Sample list of database users for testing."""
    return [
        {"username": "user1", "databaseName": "admin"},
        {"username": "user2", "databaseName": "testdb"},
        {
            "username": "__onprem_monitoring",
            "databaseName": "admin",
        },  # Should be skipped
    ]


@pytest.fixture
def sample_atlas_users():
    """Sample list of Atlas users for testing."""
    return [
        {"id": "user1", "username": "user1@example.com"},
        {"id": "user2", "username": "user2@example.com"},
    ]


@pytest.fixture
def sample_invitations():
    """Sample list of invitations for testing."""
    return [
        {"id": "invite1", "username": "invite1@example.com"},
        {"id": "invite2", "username": "invite2@example.com"},
    ]


@pytest.fixture
def paginated_response_factory():
    """Factory to create paginated API responses."""

    def _create_paginated_response(results, has_next=False):
        links = []
        if has_next:
            links.append({"rel": "next", "href": "http://example.com/next"})
        return {
            "results": results,
            "links": links,
            "totalCount": len(results),
        }

    return _create_paginated_response


@pytest.fixture
def temp_csv_file(tmp_path):
    """Create a temporary CSV file for testing."""

    def _create_csv(emails):
        csv_file = tmp_path / "test_emails.csv"
        with open(csv_file, "w") as f:
            for email in emails:
                f.write(f"{email}\n")
        return str(csv_file)

    return _create_csv
