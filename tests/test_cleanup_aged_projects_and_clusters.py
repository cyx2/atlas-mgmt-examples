"""
Tests for cleanup_aged_projects_and_clusters.py

This module tests the aged resource cleanup functionality including:
- Credential validation
- API requests
- Pagination handling
- Resource deletion (users, clusters, invitations)
- Age-based cleanup logic
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests


class TestValidateAtlasCredentials:
    """Tests for validate_atlas_credentials function."""

    def test_validate_credentials_success(self, mock_env_vars):
        """Test successful credential validation."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            module.validate_atlas_credentials()

    @pytest.mark.parametrize(
        "missing_var,present_vars",
        [
            ("ATLAS_PUBLIC_KEY", {"ATLAS_PRIVATE_KEY": "k", "ATLAS_ORG_ID": "o"}),
            ("ATLAS_PRIVATE_KEY", {"ATLAS_PUBLIC_KEY": "k", "ATLAS_ORG_ID": "o"}),
            ("ATLAS_ORG_ID", {"ATLAS_PUBLIC_KEY": "k", "ATLAS_PRIVATE_KEY": "k"}),
        ],
    )
    def test_validate_credentials_missing_var(
        self, mock_env_vars, missing_var, present_vars
    ):
        """Test validation fails when a required credential is missing."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("os.getenv") as mock_getenv:
                mock_getenv.side_effect = lambda key, default=None: present_vars.get(
                    key, default
                )

                with pytest.raises(ValueError) as excinfo:
                    module.validate_atlas_credentials()
                assert missing_var in str(excinfo.value)


class TestGetEnvVariable:
    """Tests for get_env_variable function."""

    def test_get_existing_env_variable(self, mock_env_vars):
        """Test getting an existing environment variable."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            result = module.get_env_variable("ATLAS_PUBLIC_KEY")
            assert result == "test_public_key"

    def test_get_missing_env_variable(self, mock_env_vars):
        """Test getting a missing environment variable raises error."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with pytest.raises(ValueError) as excinfo:
                module.get_env_variable("NONEXISTENT_VAR")
            assert "NONEXISTENT_VAR" in str(excinfo.value)


class TestMakeAtlasApiRequest:
    """Tests for make_atlas_api_request function."""

    def test_successful_request(self, mock_env_vars, mock_response):
        """Test successful API request."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(200, {"data": "test"})

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.make_atlas_api_request("GET", "http://test.com", auth)

                assert result is not None
                assert result.status_code == 200

    def test_failed_request_returns_none(self, mock_env_vars):
        """Test failed request returns None."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = requests.exceptions.RequestException("Error")

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.make_atlas_api_request("GET", "http://test.com", auth)

                assert result is None

    def test_request_uses_30_second_timeout(self, mock_env_vars, mock_response):
        """Test request is made with 30 second timeout."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(200)

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                module.make_atlas_api_request("GET", "http://test.com", auth)

                call_kwargs = mock_request.call_args[1]
                assert call_kwargs["timeout"] == 30


class TestGetAllPaginatedItems:
    """Tests for get_all_paginated_items function."""

    def test_single_page_response(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test handling of single page response."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                items = [{"id": "1"}, {"id": "2"}]
                mock_request.return_value = mock_response(
                    200, paginated_response_factory(items)
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_all_paginated_items("http://test.com", auth)

                assert result == items

    def test_multiple_pages_response(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test handling of multiple page response."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                page1_items = [{"id": "1"}]
                page2_items = [{"id": "2"}]

                mock_request.side_effect = [
                    mock_response(
                        200, paginated_response_factory(page1_items, has_next=True)
                    ),
                    mock_response(
                        200, paginated_response_factory(page2_items, has_next=False)
                    ),
                ]

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_all_paginated_items("http://test.com", auth)

                assert result == page1_items + page2_items

    def test_empty_response(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test handling of empty response."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(
                    200, paginated_response_factory([])
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_all_paginated_items("http://test.com", auth)

                assert result == []


class TestGetAtlasResources:
    """Tests for get_atlas_* wrapper functions."""

    def test_get_atlas_projects(
        self, mock_env_vars, mock_response, sample_projects, paginated_response_factory
    ):
        """Test getting Atlas projects."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(
                    200, paginated_response_factory(sample_projects)
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_atlas_projects("test_org", auth)

                assert len(result) == 2

    def test_get_atlas_clusters(
        self, mock_env_vars, mock_response, sample_clusters, paginated_response_factory
    ):
        """Test getting Atlas clusters."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(
                    200, paginated_response_factory(sample_clusters)
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_atlas_clusters("project123", auth)

                assert len(result) == 2


class TestDeleteAtlasResource:
    """Tests for delete_atlas_resource function."""

    @pytest.mark.parametrize(
        "resource_type,resource_id,status_code",
        [
            ("database_user", "testuser", 204),
            ("project_user", "user123", 202),
            ("cluster", "test-cluster", 202),
        ],
    )
    def test_delete_resource_success(
        self, mock_env_vars, mock_response, resource_type, resource_id, status_code
    ):
        """Test successful resource deletion for various resource types."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(status_code)

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.delete_atlas_resource(
                    resource_type, "project123", resource_id, auth
                )

                assert result is True

    def test_delete_unknown_resource_type_returns_false(self, mock_env_vars):
        """Test deletion with unknown resource type returns False."""
        with patch.dict(os.environ, mock_env_vars):
            from requests.auth import HTTPDigestAuth

            import cleanup_aged_projects_and_clusters as module

            auth = HTTPDigestAuth("user", "pass")
            result = module.delete_atlas_resource(
                "unknown_type", "project123", "resource123", auth
            )

            assert result is False

    def test_delete_resource_api_failure(self, mock_env_vars):
        """Test resource deletion when API fails returns falsy value."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = requests.exceptions.RequestException(
                    "API Error"
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.delete_atlas_resource(
                    "cluster", "project123", "test-cluster", auth
                )

                assert not result


class TestShowWarningAndConfirm:
    """Tests for show_warning_and_confirm function."""

    def test_confirm_accepted(self, mock_env_vars):
        """Test confirmation when user types exact confirmation text."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch(
                "builtins.input", return_value="REAP PROJECTS OLDER THAN 90 DAYS"
            ):
                result = module.show_warning_and_confirm("test_org")
                assert result is True

    def test_confirm_rejected(self, mock_env_vars):
        """Test confirmation when user doesn't type exact confirmation text."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("builtins.input", return_value="no"):
                result = module.show_warning_and_confirm("test_org")
                assert result is False

    def test_no_confirm_flag_skips_prompt(self, mock_env_vars):
        """Test that no_confirm=True skips the input prompt and returns True."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("builtins.input") as mock_input:
                result = module.show_warning_and_confirm("test_org", no_confirm=True)
                assert result is True
                # Verify input was never called when no_confirm is True
                mock_input.assert_not_called()


class TestCleanupFunctions:
    """Tests for cleanup_project_resources and cleanup_project_clusters functions."""

    def test_cleanup_resources_deletes_users(
        self,
        mock_env_vars,
        mock_response,
        sample_database_users,
        sample_atlas_users,
        paginated_response_factory,
    ):
        """Test cleanup deletes database and Atlas users."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = [
                    mock_response(
                        200, paginated_response_factory(sample_database_users)
                    ),
                    mock_response(204),  # Delete user1
                    mock_response(204),  # Delete user2
                    mock_response(200, paginated_response_factory(sample_atlas_users)),
                    mock_response(204),  # Delete atlas user1
                    mock_response(204),  # Delete atlas user2
                ]

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")

                # Should not raise
                module.cleanup_project_resources("project123", "test-project", auth)

    def test_cleanup_clusters_deletes_all(
        self, mock_env_vars, mock_response, sample_clusters, paginated_response_factory
    ):
        """Test cleanup deletes all clusters in project."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = [
                    mock_response(200, paginated_response_factory(sample_clusters)),
                    mock_response(202),
                    mock_response(202),
                ]

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")

                module.cleanup_project_clusters("project123", "test-project", auth)


class TestMain:
    """Tests for main function."""

    def test_main_cancelled_by_user(self, mock_env_vars):
        """Test main function when user cancels."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py"]):
                with patch("builtins.input", return_value="no"):
                    result = module.main()
                    assert result == 0

    def test_main_requires_exact_confirmation_text(self, mock_env_vars):
        """Test main function requires exact confirmation text and cancels if incorrect."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py"]):
                # Test with incorrect confirmation text (close but not exact)
                incorrect_confirmations = [
                    "reap projects older than 90 days",  # lowercase
                    "REAP PROJECTS OLDER THAN 90 DAYS ",  # trailing space
                    " REAP PROJECTS OLDER THAN 90 DAYS",  # leading space
                    "REAP PROJECTS OLDER THAN 90 DAYS.",  # extra period
                    "yes",  # simple yes
                    "",  # empty string
                ]

                for incorrect_confirmation in incorrect_confirmations:
                    with patch("builtins.input", return_value=incorrect_confirmation):
                        with patch("requests.request") as mock_request:
                            # If confirmation fails, main() should return early without making API calls
                            result = module.main()
                            assert result == 0, f"Should cancel with confirmation: '{incorrect_confirmation}'"
                            # Verify no API requests were made when confirmation fails
                            # get_atlas_projects() is called after confirmation, so it should never be called
                            assert mock_request.call_count == 0, (
                                f"No API calls should be made when confirmation fails. "
                                f"Got {mock_request.call_count} calls with confirmation: '{incorrect_confirmation}'"
                            )

    def test_main_no_projects_found(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test main function when no projects found."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py"]):
                with patch(
                    "builtins.input", return_value="REAP PROJECTS OLDER THAN 90 DAYS"
                ):
                    with patch("requests.request") as mock_request:
                        mock_request.return_value = mock_response(
                            200, paginated_response_factory([])
                        )

                        result = module.main()
                        assert result == 1

    def test_main_keyboard_interrupt(self, mock_env_vars):
        """Test main function handles KeyboardInterrupt."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py"]):
                with patch("builtins.input", side_effect=KeyboardInterrupt):
                    result = module.main()
                    assert result == 1

    def test_main_processes_old_projects(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test main function processes old projects correctly."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            # Create an old project (older than 120 days)
            old_date = (datetime.now(timezone.utc) - timedelta(days=150)).isoformat()
            old_project = {
                "id": "old_project",
                "name": "old-test-project",
                "created": old_date,
            }

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py"]):
                with patch(
                    "builtins.input", return_value="REAP PROJECTS OLDER THAN 90 DAYS"
                ):
                    with patch("requests.request") as mock_request:
                        mock_request.side_effect = [
                            mock_response(200, paginated_response_factory([old_project])),
                            mock_response(200, []),  # group invitations
                            mock_response(200, paginated_response_factory([])),  # db users
                            mock_response(
                                200, paginated_response_factory([])
                            ),  # atlas users
                            mock_response(200, paginated_response_factory([])),  # clusters
                        ]

                        result = module.main()
                        assert result == 0

    def test_main_with_no_confirm_flag(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test main function with --no-confirm flag skips confirmation."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            # Create an old project (older than 120 days)
            old_date = (datetime.now(timezone.utc) - timedelta(days=150)).isoformat()
            old_project = {
                "id": "old_project",
                "name": "old-test-project",
                "created": old_date,
            }

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py", "--no-confirm"]):
                with patch("builtins.input") as mock_input:
                    with patch("requests.request") as mock_request:
                        mock_request.side_effect = [
                            mock_response(200, paginated_response_factory([old_project])),
                            mock_response(200, []),  # group invitations
                            mock_response(200, paginated_response_factory([])),  # db users
                            mock_response(
                                200, paginated_response_factory([])
                            ),  # atlas users
                            mock_response(200, paginated_response_factory([])),  # clusters
                        ]

                        result = module.main()
                        assert result == 0
                        # Verify input was never called when --no-confirm is used
                        mock_input.assert_not_called()

    def test_main_with_no_confirm_flag_no_projects(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test main function with --no-confirm flag when no projects found."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("sys.argv", ["cleanup_aged_projects_and_clusters.py", "--no-confirm"]):
                with patch("builtins.input") as mock_input:
                    with patch("requests.request") as mock_request:
                        mock_request.return_value = mock_response(
                            200, paginated_response_factory([])
                        )

                        result = module.main()
                        assert result == 1
                        # Verify input was never called when --no-confirm is used
                        mock_input.assert_not_called()


class TestModuleInitialization:
    """Regression tests that verify load_dotenv() is called at module level.

    These tests ensure that load_dotenv() is called during module import,
    not just in main(), preventing the authentication bug where environment
    variables weren't loaded before functions tried to read them.
    """

    def test_load_dotenv_called_at_module_level(self):
        """
        Test that load_dotenv() is called at module level, not just in main().
        This ensures environment variables are loaded before functions try to read them.
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

            if "cleanup_aged_projects_and_clusters" in sys.modules:
                del sys.modules["cleanup_aged_projects_and_clusters"]

            # Patch dotenv.load_dotenv BEFORE importing the module
            # When the module does "from dotenv import load_dotenv", it will get our patched version
            with patch("dotenv.load_dotenv", wraps=lambda: None) as mock_load:
                # Import should trigger load_dotenv() at module level
                import cleanup_aged_projects_and_clusters as module

                # Verify load_dotenv was called during import
                assert (
                    mock_load.called
                ), "load_dotenv() should be called at module level during import"

                # Verify that get_env_variable can read from environment
                # (This script uses get_env_variable helper function)
                assert module.get_env_variable("ATLAS_PUBLIC_KEY") == "test_public_key"
                assert (
                    module.get_env_variable("ATLAS_PRIVATE_KEY") == "test_private_key"
                )
                assert module.get_env_variable("ATLAS_ORG_ID") == "test_org_id"
