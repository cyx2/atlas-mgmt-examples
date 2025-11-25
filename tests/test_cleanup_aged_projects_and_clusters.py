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


class TestGetAtlasOrgInvitations:
    """Tests for get_atlas_org_invitations function."""

    def test_get_invitations_list_response(
        self, mock_env_vars, mock_response, sample_invitations
    ):
        """Test getting invitations when API returns a list."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(200, sample_invitations)

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_atlas_org_invitations("org123", auth)

                assert len(result) == 2

    def test_get_invitations_api_failure_returns_empty(self, mock_env_vars):
        """Test handling API failure when getting invitations."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = requests.exceptions.RequestException(
                    "API Error"
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.get_atlas_org_invitations("org123", auth)

                assert result == []


class TestDeleteAtlasOrgInvitation:
    """Tests for delete_atlas_org_invitation function."""

    def test_delete_invitation_success(self, mock_env_vars, mock_response):
        """Test successful invitation deletion."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(204)

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.delete_atlas_org_invitation("org123", "invite123", auth)

                assert result is True

    def test_delete_invitation_failure(self, mock_env_vars):
        """Test failed invitation deletion."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.side_effect = requests.exceptions.RequestException(
                    "API Error"
                )

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                result = module.delete_atlas_org_invitation("org123", "invite123", auth)

                assert result is False


class TestDeleteInvitationsForOldProjects:
    """Tests for delete_invitations_for_old_projects function."""

    def test_deletes_all_invitations_when_old_projects_exist(
        self, mock_env_vars, mock_response, sample_invitations
    ):
        """Test all invitations are deleted when old projects exist."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

            with patch("requests.request") as mock_request:
                mock_request.return_value = mock_response(204)

                from requests.auth import HTTPDigestAuth

                auth = HTTPDigestAuth("user", "pass")
                old_project_ids = {"project1"}

                successful, failed = module.delete_invitations_for_old_projects(
                    "org123", sample_invitations, old_project_ids, auth
                )

                assert successful == 2
                assert failed == 0

    def test_no_deletion_when_no_old_projects(self, mock_env_vars, sample_invitations):
        """Test no invitations deleted when no old projects exist."""
        with patch.dict(os.environ, mock_env_vars):
            from requests.auth import HTTPDigestAuth

            import cleanup_aged_projects_and_clusters as module

            auth = HTTPDigestAuth("user", "pass")

            successful, failed = module.delete_invitations_for_old_projects(
                "org123", sample_invitations, set(), auth
            )

            assert successful == 0
            assert failed == 0


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

            with patch("builtins.input", return_value="no"):
                result = module.main()
                assert result == 0

    def test_main_no_projects_found(
        self, mock_env_vars, mock_response, paginated_response_factory
    ):
        """Test main function when no projects found."""
        with patch.dict(os.environ, mock_env_vars):
            import cleanup_aged_projects_and_clusters as module

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

            with patch(
                "builtins.input", return_value="REAP PROJECTS OLDER THAN 90 DAYS"
            ):
                with patch("requests.request") as mock_request:
                    mock_request.side_effect = [
                        mock_response(200, paginated_response_factory([old_project])),
                        mock_response(200, []),  # invitations
                        mock_response(200, paginated_response_factory([])),  # db users
                        mock_response(
                            200, paginated_response_factory([])
                        ),  # atlas users
                        mock_response(200, paginated_response_factory([])),  # clusters
                    ]

                    result = module.main()
                    assert result == 0
