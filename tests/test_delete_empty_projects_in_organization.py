"""
Tests for delete_empty_projects_in_organization.py

This module tests the empty projects cleanup functionality including:
- AtlasAPI class
- AtlasEmptyProjectsCleaner class
- Credential validation
- Project deletion logic
"""

import json
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests


class TestAtlasAPI:
    """Tests for AtlasAPI class."""

    def test_init_success(self, mock_env_vars, mock_response):
        """Test successful AtlasAPI initialization."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                assert api.org_id == "test_org_id"
                assert api.public_key == "test_public_key"
                assert api.private_key == "test_private_key"

    def test_init_missing_credentials(self):
        """Test AtlasAPI initialization with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            from delete_empty_projects_in_organization import AtlasAPI

            with pytest.raises(ValueError) as excinfo:
                AtlasAPI()
            assert "Missing required Atlas API credentials" in str(excinfo.value)

    def test_init_invalid_credentials(self, mock_env_vars):
        """Test AtlasAPI initialization with invalid credentials."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.side_effect = requests.exceptions.RequestException(
                    "Auth failed"
                )

                from delete_empty_projects_in_organization import AtlasAPI

                with pytest.raises(ValueError) as excinfo:
                    AtlasAPI()
                assert "Failed to authenticate" in str(excinfo.value)

    def test_init_org_not_found(self, mock_env_vars, mock_response):
        """Test AtlasAPI initialization when org not found."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # Return different org IDs
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "different_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                with pytest.raises(ValueError) as excinfo:
                    AtlasAPI()
                assert "not found" in str(excinfo.value)

    def test_make_request_get(self, mock_env_vars, mock_response):
        """Test _make_request with GET method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                # Make another GET request
                mock_get.return_value = mock_response(200, {"data": "test"})
                result, success = api._make_request("get", "/test")

                assert success is True
                assert result == {"data": "test"}

    def test_make_request_post(self, mock_env_vars, mock_response):
        """Test _make_request with POST method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                with patch("requests.post") as mock_post:
                    mock_post.return_value = mock_response(201, {"id": "new"})
                    result, success = api._make_request(
                        "post", "/test", {"name": "test"}
                    )

                    assert success is True

    def test_make_request_delete(self, mock_env_vars, mock_response):
        """Test _make_request with DELETE method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                with patch("requests.delete") as mock_delete:
                    mock_delete.return_value = mock_response(204, {})
                    result, success = api._make_request("delete", "/test")

                    assert success is True

    def test_make_request_with_retry(self, mock_env_vars, mock_response):
        """Test _make_request retries on failure."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # First call for init
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                # Second call fails, third succeeds
                mock_get.side_effect = [
                    requests.exceptions.RequestException("Temp error"),
                    mock_response(200, {"data": "test"}),
                ]

                with patch("time.sleep"):  # Skip sleep
                    result, success = api._make_request("get", "/test", retry=1)

                    # Should succeed after retry
                    assert success is True

    def test_get_projects_in_org(
        self, mock_env_vars, mock_response, sample_projects, paginated_response_factory
    ):
        """Test get_projects_in_org method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # Init call
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                # Projects call
                mock_get.return_value = mock_response(
                    200, paginated_response_factory(sample_projects)
                )

                result = api.get_projects_in_org()

                assert len(result) == 2

    def test_get_projects_in_org_pagination(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test get_projects_in_org with multiple pages."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # Init call
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                page1 = [{"id": "p1", "name": "project1"}]
                page2 = [{"id": "p2", "name": "project2"}]

                # Pagination calls
                mock_get.side_effect = [
                    mock_response(
                        200, paginated_response_factory(page1, has_next=True)
                    ),
                    mock_response(
                        200, paginated_response_factory(page2, has_next=False)
                    ),
                ]

                result = api.get_projects_in_org()

                assert len(result) == 2

    def test_get_clusters_in_project(
        self, mock_env_vars, mock_response, sample_clusters, paginated_response_factory
    ):
        """Test get_clusters_in_project method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # Init call
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                # Clusters call
                mock_get.return_value = mock_response(
                    200, paginated_response_factory(sample_clusters)
                )

                result = api.get_clusters_in_project("project123")

                assert len(result) == 2

    def test_get_clusters_in_project_empty(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test get_clusters_in_project with empty result."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                mock_get.return_value = mock_response(
                    200, paginated_response_factory([])
                )

                result = api.get_clusters_in_project("project123")

                assert len(result) == 0

    def test_delete_project_success(self, mock_env_vars, mock_response):
        """Test delete_project method success."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                with patch("requests.delete") as mock_delete:
                    mock_delete.return_value = mock_response(204, {})

                    result = api.delete_project("project123")

                    assert result is True

    def test_delete_project_failure(self, mock_env_vars, mock_response):
        """Test delete_project method failure."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import AtlasAPI

                api = AtlasAPI()

                with patch("requests.delete") as mock_delete:
                    mock_delete.side_effect = requests.exceptions.RequestException(
                        "Error"
                    )

                    result = api.delete_project("project123")

                    assert result is False


class TestAtlasEmptyProjectsCleaner:
    """Tests for AtlasEmptyProjectsCleaner class."""

    def test_init(self, mock_env_vars, mock_response):
        """Test AtlasEmptyProjectsCleaner initialization."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import (
                    AtlasEmptyProjectsCleaner,
                )

                cleaner = AtlasEmptyProjectsCleaner()

                assert cleaner.deleted_projects == []
                assert cleaner.skipped_projects == []

    def test_delete_empty_projects_dry_run(
        self, mock_env_vars, mock_response, sample_projects, paginated_response_factory
    ):
        """Test delete_empty_projects in dry run mode."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                # Init call
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import (
                    AtlasEmptyProjectsCleaner,
                )

                cleaner = AtlasEmptyProjectsCleaner()

                # Projects and clusters calls
                mock_get.side_effect = [
                    mock_response(200, paginated_response_factory(sample_projects[:1])),
                    mock_response(
                        200, paginated_response_factory([])
                    ),  # Empty clusters
                ]

                cleaner.delete_empty_projects(dry_run=True)

                assert len(cleaner.deleted_projects) == 1
                assert cleaner.deleted_projects[0]["deleted"] is False
                assert cleaner.deleted_projects[0]["reason"] == "dry_run"

    def test_delete_empty_projects_actual_delete(
        self, mock_env_vars, mock_response, sample_projects, paginated_response_factory
    ):
        """Test delete_empty_projects with actual deletion."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import (
                    AtlasEmptyProjectsCleaner,
                )

                cleaner = AtlasEmptyProjectsCleaner()

                # Mock API calls
                mock_get.side_effect = [
                    mock_response(200, paginated_response_factory(sample_projects[:1])),
                    mock_response(
                        200, paginated_response_factory([])
                    ),  # Empty clusters
                ]

                with patch("requests.delete") as mock_delete:
                    mock_delete.return_value = mock_response(204, {})

                    cleaner.delete_empty_projects(dry_run=False)

                    assert len(cleaner.deleted_projects) == 1
                    assert cleaner.deleted_projects[0]["deleted"] is True

    def test_delete_empty_projects_skips_non_empty(
        self,
        mock_env_vars,
        mock_response,
        sample_projects,
        sample_clusters,
        paginated_response_factory,
    ):
        """Test that projects with clusters are skipped."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import (
                    AtlasEmptyProjectsCleaner,
                )

                cleaner = AtlasEmptyProjectsCleaner()

                mock_get.side_effect = [
                    mock_response(200, paginated_response_factory(sample_projects[:1])),
                    mock_response(
                        200, paginated_response_factory(sample_clusters)
                    ),  # Has clusters
                ]

                cleaner.delete_empty_projects(dry_run=False)

                assert len(cleaner.skipped_projects) == 1
                assert len(cleaner.deleted_projects) == 0

    def test_generate_report(self, mock_env_vars, mock_response, tmp_path):
        """Test generate_report method."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import (
                    AtlasEmptyProjectsCleaner,
                )

                cleaner = AtlasEmptyProjectsCleaner()

                # Add some test data
                cleaner.deleted_projects = [
                    {
                        "id": "p1",
                        "name": "project1",
                        "deleted": True,
                        "reason": "success",
                    }
                ]
                cleaner.skipped_projects = [
                    {"id": "p2", "name": "project2", "cluster_count": 2}
                ]

                report_file = tmp_path / "report.json"
                with patch("builtins.open", mock_open()) as mock_file:
                    with patch(
                        "delete_empty_projects_in_organization.open",
                        mock_open(),
                        create=True,
                    ):
                        report = cleaner.generate_report()

                assert report["summary"]["total_projects_scanned"] == 2
                assert report["summary"]["empty_projects_found"] == 1
                assert report["summary"]["successful_deletions"] == 1


class TestValidateCredentials:
    """Tests for validate_credentials function."""

    def test_validate_credentials_success(self, mock_env_vars):
        """Test successful credential validation."""
        with patch.dict(os.environ, mock_env_vars):
            from delete_empty_projects_in_organization import validate_credentials

            # Should not raise
            validate_credentials()

    def test_validate_credentials_missing(self):
        """Test validation with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            from delete_empty_projects_in_organization import validate_credentials

            with pytest.raises(ValueError) as excinfo:
                validate_credentials()
            assert "Missing required environment variables" in str(excinfo.value)


class TestMain:
    """Tests for main function."""

    def test_main_dry_run(
        self, mock_env_vars, mock_response, sample_projects, paginated_response_factory
    ):
        """Test main function in dry run mode."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import main

                with patch("sys.argv", ["script", "--dry-run"]):
                    mock_get.side_effect = [
                        # Init call
                        mock_response(200, {"results": [{"id": "test_org_id"}]}),
                        # Projects call
                        mock_response(200, paginated_response_factory([])),
                    ]

                    with patch("builtins.open", mock_open()):
                        result = main()
                        assert result == 0

    def test_main_cancelled(self, mock_env_vars, mock_response):
        """Test main function when user cancels."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import main

                with patch("sys.argv", ["script"]):
                    with patch("builtins.input", return_value="no"):
                        result = main()
                        assert result == 0

    def test_main_keyboard_interrupt(self, mock_env_vars, mock_response):
        """Test main function handles KeyboardInterrupt."""
        with patch.dict(os.environ, mock_env_vars):
            with patch("requests.get") as mock_get:
                mock_get.return_value = mock_response(
                    200, {"results": [{"id": "test_org_id"}]}
                )

                from delete_empty_projects_in_organization import main

                with patch("sys.argv", ["script"]):
                    with patch("builtins.input", side_effect=KeyboardInterrupt):
                        result = main()
                        assert result == 1

    def test_main_missing_credentials(self):
        """Test main function with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            from delete_empty_projects_in_organization import main

            with patch("sys.argv", ["script"]):
                result = main()
                assert result == 1


class TestModuleInitialization:
    """Regression tests that verify load_dotenv() is called at module level.

    These tests ensure that load_dotenv() is called during module import,
    not just in main(), preventing the authentication bug where environment
    variables weren't loaded before classes tried to read them.
    """

    def test_load_dotenv_called_at_module_level(self, mock_response):
        """
        Test that load_dotenv() is called at module level, not just in main().
        This ensures environment variables are loaded before classes try to read them.
        """
        with patch.dict(
            os.environ,
            {
                "ATLAS_PUBLIC_KEY": "test_public_key",
                "ATLAS_PRIVATE_KEY": "test_private_key",
                "ATLAS_ORG_ID": "test_org_id",
            },
            clear=True,
        ):
            # Temporarily disable the autouse mock_load_dotenv fixture
            # by patching dotenv.load_dotenv before module import
            import importlib

            if "delete_empty_projects_in_organization" in sys.modules:
                del sys.modules["delete_empty_projects_in_organization"]

            # Patch dotenv.load_dotenv BEFORE importing the module
            # When the module does "from dotenv import load_dotenv", it will get our patched version
            with patch("dotenv.load_dotenv", wraps=lambda: None) as mock_load:
                # Import should trigger load_dotenv() at module level
                from delete_empty_projects_in_organization import AtlasAPI

                # Verify load_dotenv was called during import
                assert (
                    mock_load.called
                ), "load_dotenv() should be called at module level during import"

                # Now instantiate - should work because env vars are in os.environ
                with patch("requests.get") as mock_get:
                    mock_get.return_value = mock_response(
                        200, {"results": [{"id": "test_org_id"}]}
                    )
                    api = AtlasAPI()
                    assert api.org_id == "test_org_id"
                    assert api.public_key == "test_public_key"
                    assert api.private_key == "test_private_key"
