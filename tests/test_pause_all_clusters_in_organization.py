"""
Tests for pause_all_clusters_in_organization.py

This module tests the cluster pause functionality including:
- Credential validation
- API requests
- Pagination handling
- Cluster pause operations
"""

import os
from unittest.mock import MagicMock, patch
import pytest
import requests


class TestValidateAtlasCredentials:
    """Tests for validate_atlas_credentials function."""

    def test_validate_credentials_success(self):
        """Test successful credential validation."""
        import pause_all_clusters_in_organization as module
        
        # Set module-level vars to valid values
        module.PUBLIC_KEY = "test_key"
        module.PRIVATE_KEY = "test_key"
        module.ORGANIZATION_ID = "test_org"
        
        # Should not raise
        module.validate_atlas_credentials()

    def test_validate_credentials_missing_public_key(self):
        """Test validation fails with missing public key."""
        import pause_all_clusters_in_organization as module
        
        # Set module-level vars to test missing PUBLIC_KEY
        module.PUBLIC_KEY = None
        module.PRIVATE_KEY = "test_key"
        module.ORGANIZATION_ID = "test_org"
        
        with pytest.raises(ValueError) as excinfo:
            module.validate_atlas_credentials()
        assert "ATLAS_PUBLIC_KEY" in str(excinfo.value)

    def test_validate_credentials_missing_private_key(self):
        """Test validation fails with missing private key."""
        import pause_all_clusters_in_organization as module
        
        # Set module-level vars to test missing PRIVATE_KEY
        module.PUBLIC_KEY = "test_key"
        module.PRIVATE_KEY = None
        module.ORGANIZATION_ID = "test_org"
        
        with pytest.raises(ValueError) as excinfo:
            module.validate_atlas_credentials()
        assert "ATLAS_PRIVATE_KEY" in str(excinfo.value)

    def test_validate_credentials_missing_org_id(self):
        """Test validation fails with missing org ID."""
        import pause_all_clusters_in_organization as module
        
        # Set module-level vars to test missing ORGANIZATION_ID
        module.PUBLIC_KEY = "test_key"
        module.PRIVATE_KEY = "test_key"
        module.ORGANIZATION_ID = None
        
        with pytest.raises(ValueError) as excinfo:
            module.validate_atlas_credentials()
        assert "ATLAS_ORG_ID" in str(excinfo.value)


class TestMakeAtlasApiRequest:
    """Tests for make_atlas_api_request function."""

    def test_successful_get_request(self, mock_response):
        """Test successful GET request."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(200, {"data": "test"})
                            
                            result = module.make_atlas_api_request("GET", "http://test.com")
                            
                            assert result is not None
                            assert result.status_code == 200

    def test_successful_patch_request(self, mock_response):
        """Test successful PATCH request."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(200)
                            
                            result = module.make_atlas_api_request(
                                "PATCH", "http://test.com", json={"paused": True}
                            )
                            
                            assert result is not None

    def test_failed_request_returns_none(self):
        """Test failed request returns None."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = requests.exceptions.RequestException("Error")
                            
                            result = module.make_atlas_api_request("GET", "http://test.com")
                            
                            assert result is None


class TestGetAllPaginatedProjects:
    """Tests for get_all_paginated_projects function."""

    def test_single_page_projects(self, mock_response, sample_projects, paginated_response_factory):
        """Test retrieving projects from single page."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
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
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
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

    def test_api_failure(self):
        """Test handling API failure."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = requests.exceptions.RequestException("Error")
                            
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
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory([])),  # Empty clusters
                            ]
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            # Should succeed - no clusters to pause
                            assert result is True

    def test_get_clusters_with_paginated_response_format(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test clusters are properly extracted from paginated response format."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        running_clusters = [{"name": "cluster1", "paused": False}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory(running_clusters)),
                                mock_response(200),  # Pause response
                            ]
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            assert result is True


class TestPauseAllClustersInOrg:
    """Tests for pause_all_clusters_in_org function."""

    def test_pause_clusters_success(self, mock_response, sample_projects, sample_clusters, paginated_response_factory):
        """Test successful cluster pause operation."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        # Use only running cluster
                        running_clusters = [{"name": "cluster1", "paused": False}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                # Get projects
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                # Get clusters
                                mock_response(200, paginated_response_factory(running_clusters)),
                                # Pause cluster
                                mock_response(200),
                            ]
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            assert result is True

    def test_pause_clusters_no_org_id(self):
        """Test handling missing org ID."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        result = module.pause_all_clusters_in_org("")
                        
                        assert result is False

    def test_pause_clusters_no_projects(self, mock_response, paginated_response_factory):
        """Test handling when no projects found."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory([])
                            )
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            assert result is False

    def test_pause_skips_already_paused(self, mock_response, sample_projects, paginated_response_factory):
        """Test that already paused clusters are skipped."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        paused_clusters = [{"name": "cluster1", "paused": True}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory(paused_clusters)),
                            ]
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            # Should succeed - no clusters needed pausing
                            assert result is True

    def test_pause_skips_missing_project_id(self, mock_response, paginated_response_factory):
        """Test skipping projects with missing ID."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        projects_no_id = [{"name": "project1"}]  # Missing ID
                        
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(
                                200, paginated_response_factory(projects_no_id)
                            )
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            assert result is True

    def test_pause_handles_failures(self, mock_response, sample_projects, paginated_response_factory):
        """Test handling pause failures."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        running_clusters = [{"name": "cluster1", "paused": False}]
                        
                        with patch("requests.request") as mock_request:
                            mock_request.side_effect = [
                                mock_response(200, paginated_response_factory(sample_projects[:1])),
                                mock_response(200, paginated_response_factory(running_clusters)),
                                # Pause fails
                                requests.exceptions.RequestException("Error"),
                            ]
                            
                            result = module.pause_all_clusters_in_org("test_org")
                            
                            assert result is False


class TestMain:
    """Tests for main function."""

    def test_main_cancelled(self):
        """Test main function when user cancels."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="no"):
                            result = module.main()
                            assert result == 0

    def test_main_confirmed_success(self, mock_response, sample_projects, paginated_response_factory):
        """Test main function with successful execution."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="PAUSE ALL CLUSTERS"):
                            with patch("requests.request") as mock_request:
                                mock_request.side_effect = [
                                    mock_response(200, paginated_response_factory(sample_projects[:1])),
                                    mock_response(200, paginated_response_factory([])),  # No clusters
                                ]
                                
                                result = module.main()
                                # No clusters to pause, but operation succeeds
                                assert result == 0

    def test_main_keyboard_interrupt(self):
        """Test main function handles KeyboardInterrupt."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("builtins.input", side_effect=KeyboardInterrupt):
                            result = module.main()
                            assert result == 1

    def test_main_unexpected_exception(self):
        """Test main function handles unexpected exceptions."""
        env_vars = {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch("pause_all_clusters_in_organization.PUBLIC_KEY", "test_key"):
                with patch("pause_all_clusters_in_organization.PRIVATE_KEY", "test_key"):
                    with patch("pause_all_clusters_in_organization.ORGANIZATION_ID", "test_org"):
                        import pause_all_clusters_in_organization as module
                        
                        with patch("builtins.input", return_value="PAUSE ALL CLUSTERS"):
                            with patch.object(module, "pause_all_clusters_in_org", side_effect=Exception("Error")):
                                result = module.main()
                                assert result == 1

