"""
Tests for delete_all_clusters_in_organization.py

This module tests the cluster deletion functionality including:
- Credential validation
- API requests
- Pagination handling
- Cluster deletion across all projects
"""

import os
from unittest.mock import MagicMock, patch
import pytest
import requests


class TestValidateAtlasCredentials:
    """Tests for validate_atlas_credentials function."""

    def test_validate_credentials_success(self):
        """Test successful credential validation."""
        import delete_all_clusters_in_organization as module
        
        # Set module-level vars to valid values
        module.PUBLIC_KEY = "test_public_key"
        module.PRIVATE_KEY = "test_private_key"
        module.ORGANIZATION_ID = "test_org_id"
        
        # Should not raise
        module.validate_atlas_credentials()

    def test_validate_credentials_missing_vars(self):
        """Test validation fails with missing credentials."""
        import delete_all_clusters_in_organization as module
        
        # Module-level vars are None by default (set at runtime in main())
        # Set some vars to test missing PUBLIC_KEY
        module.PUBLIC_KEY = None
        module.PRIVATE_KEY = "test_key"
        module.ORGANIZATION_ID = "test_org"
        
        with pytest.raises(ValueError) as excinfo:
            module.validate_atlas_credentials()
        assert "ATLAS_PUBLIC_KEY" in str(excinfo.value)


class TestMakeAtlasApiRequest:
    """Tests for make_atlas_api_request function."""

    def test_successful_request(self, mock_response):
        """Test successful API request."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(200, {"data": "test"})
                            
                            result = module.make_atlas_api_request("GET", "http://test.com")
                            
                            assert result is not None
                            assert result.status_code == 200

    def test_failed_request_returns_none(self):
        """Test failed request returns None."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = requests.exceptions.RequestException("Error")
                            
                            result = module.make_atlas_api_request("GET", "http://test.com")
                            
                            assert result is None


class TestGetAllPaginatedProjects:
    """Tests for get_all_paginated_projects function."""

    def test_single_page_projects(self, mock_response, sample_projects, paginated_response_factory):
        """Test retrieving projects from single page."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory(sample_projects)
                            )
                            
                            from requests.auth import HTTPDigestAuth
                            auth = HTTPDigestAuth("user", "pass")
                            headers = {"Content-Type": "application/json"}
                            
                            result = module.get_all_paginated_projects("org123", auth, headers)
                            
                            assert len(result) == 2

    def test_multiple_pages_projects(self, mock_response, paginated_response_factory):
        """Test retrieving projects from multiple pages."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        page1 = [{"id": "p1", "name": "project1"}]
                        page2 = [{"id": "p2", "name": "project2"}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(page1, has_next=True)),
                                mock_response(200, paginated_response_factory(page2, has_next=False)),
                            ]
                            
                            from requests.auth import HTTPDigestAuth
                            auth = HTTPDigestAuth("user", "pass")
                            headers = {"Content-Type": "application/json"}
                            
                            result = module.get_all_paginated_projects("org123", auth, headers)
                            
                            assert len(result) == 2

    def test_empty_projects(self, mock_response, paginated_response_factory):
        """Test handling empty project list."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory([])
                            )
                            
                            from requests.auth import HTTPDigestAuth
                            auth = HTTPDigestAuth("user", "pass")
                            headers = {"Content-Type": "application/json"}
                            
                            result = module.get_all_paginated_projects("org123", auth, headers)
                            
                            assert len(result) == 0


class TestGetAllPaginatedClusters:
    """Tests for cluster fetching with pagination responses."""

    def test_get_clusters_empty_response(self, mock_response, sample_projects, paginated_response_factory):
        """Test handling empty cluster list."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory([])),  # Empty clusters
                            ]
                            
                            result = module.delete_all_clusters_in_org("test_org")
                            
                            # Should succeed - no clusters to delete
                            assert result is True

    def test_get_clusters_with_paginated_response_format(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test clusters are properly extracted from paginated response format."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory(sample_clusters[:1])),
                                mock_response(202),  # Delete response
                            ]
                            
                            result = module.delete_all_clusters_in_org("test_org")
                            
                            assert result is True


class TestDeleteAllClustersInOrg:
    """Tests for delete_all_clusters_in_org function."""

    def test_delete_clusters_success(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test successful cluster deletion."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                # Get projects
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                # Get clusters for project1
                                mock_response(200, paginated_response_factory(sample_clusters[:1])),
                                # Delete cluster
                                mock_response(202),
                            ]
                            
                            result = module.delete_all_clusters_in_org("test_org")
                            
                            assert result is True

    def test_delete_clusters_no_org_id(self):
        """Test handling missing org ID."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        result = module.delete_all_clusters_in_org("")
                        
                        assert result is False

    def test_delete_clusters_no_projects(self, mock_response, paginated_response_factory):
        """Test handling when no projects found."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory([])
                            )
                            
                            result = module.delete_all_clusters_in_org("test_org")
                            
                            assert result is False

    def test_delete_clusters_with_failures(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test handling cluster deletion failures."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                # Get projects
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                # Get clusters
                                mock_response(200, paginated_response_factory(sample_clusters[:1])),
                                # Delete cluster fails
                                mock_response(500),
                            ]
                            
                            # The last call returns 500, so raise_for_status will raise
                            with patch.object(mock_request.return_value, 'raise_for_status') as mock_raise:
                                mock_raise.side_effect = requests.exceptions.HTTPError("500 Server Error")
                                
                                # This will fail because the delete request fails
                                result = module.delete_all_clusters_in_org("test_org")
                                
                                # When there are failures, it returns False
                                assert result is False

    def test_delete_clusters_skips_missing_project_id(self, mock_response, paginated_response_factory):
        """Test skipping projects with missing ID."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        projects_with_missing_id = [{"name": "no-id-project"}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory(projects_with_missing_id)
                            )
                            
                            result = module.delete_all_clusters_in_org("test_org")
                            
                            # Should succeed as no clusters to delete
                            assert result is True


class TestMain:
    """Tests for main function."""

    def test_main_cancelled_by_user(self):
        """Test main function when user cancels."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="no"):
                            result = module.main()
                            assert result == 0

    def test_main_confirmed_success(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test main function with successful execution."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="DELETE ALL CLUSTERS"):
                            with patch("requests.request") as mock_request:
                                mock_request.side_effect = [
                                    mock_response(200, paginated_response_factory(sample_projects[:1])),
                                    mock_response(200, paginated_response_factory(sample_clusters[:1])),
                                    mock_response(202),
                                ]
                                
                                result = module.main()
                                assert result == 0

    def test_main_keyboard_interrupt(self):
        """Test main function handles KeyboardInterrupt."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("builtins.input", side_effect=KeyboardInterrupt):
                            result = module.main()
                            assert result == 1

    def test_main_unexpected_exception(self):
        """Test main function handles unexpected exceptions."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with patch("delete_all_clusters_in_organization.PUBLIC_KEY", "test_public_key"):
                with patch("delete_all_clusters_in_organization.PRIVATE_KEY", "test_private_key"):
                    with patch("delete_all_clusters_in_organization.ORGANIZATION_ID", "test_org_id"):
                        import delete_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="DELETE ALL CLUSTERS"):
                            with patch.object(module, "delete_all_clusters_in_org", side_effect=Exception("Unexpected")):
                                result = module.main()
                                assert result == 1

