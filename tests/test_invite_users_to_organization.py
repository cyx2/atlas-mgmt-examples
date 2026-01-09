"""
Tests for invite_users_to_organization.py

This module tests the user invitation functionality including:
- Email loading from CSV
- Email validation
- API requests
- User invitation process
"""

import logging
import os
import sys
from unittest.mock import MagicMock, patch, mock_open
import pytest
import requests


class TestLoadEmailsFromCsv:
    """Tests for load_emails_from_csv function."""

    def test_load_emails_success(self, temp_csv_file):
        """Test successful email loading from CSV."""
        emails = ["user1@example.com", "user2@example.com"]
        csv_path = temp_csv_file(emails)
        
        # Need to import without triggering module-level code
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            # Mock the csv file read at module level
            with patch("builtins.open", mock_open(read_data="user1@example.com\nuser2@example.com\n")):
                import importlib
                
                # Create a simple test for the function logic
                from invite_users_to_organization import load_emails_from_csv
                
                result = load_emails_from_csv(csv_path)
                
                assert len(result) == 2
                assert "user1@example.com" in result
                assert "user2@example.com" in result

    def test_load_emails_empty_rows(self, temp_csv_file):
        """Test loading emails with empty rows."""
        emails = ["user1@example.com", "", "user2@example.com"]
        csv_path = temp_csv_file(emails)
        
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            from invite_users_to_organization import load_emails_from_csv
            
            result = load_emails_from_csv(csv_path)
            
            # Should skip empty rows
            assert len(result) == 2

    def test_load_emails_file_not_found(self):
        """Test handling of missing CSV file."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            from invite_users_to_organization import load_emails_from_csv
            
            with pytest.raises(FileNotFoundError):
                load_emails_from_csv("/nonexistent/path.csv")

    def test_load_emails_strips_whitespace(self, temp_csv_file):
        """Test that whitespace is stripped from emails."""
        csv_content = "  user1@example.com  \n  user2@example.com  "
        
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data=csv_content)):
                from invite_users_to_organization import load_emails_from_csv
                
                # The function will try to open the file, so we need to pass a path
                # but the mock will handle it
                with patch("csv.reader") as mock_reader:
                    mock_reader.return_value = [["  user1@example.com  "], ["  user2@example.com  "]]
                    result = load_emails_from_csv("test.csv")
                    
                    for email in result:
                        assert email == email.strip()


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_valid_emails(self):
        """Test validation of valid email formats."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                valid_emails = [
                    "user@example.com",
                    "user.name@example.com",
                    "user+tag@example.com",
                    "user123@example.co.uk",
                    "user@subdomain.example.com",
                ]
                
                for email in valid_emails:
                    assert invite_users_to_organization.validate_email(email) is True, f"Failed for {email}"

    def test_invalid_emails(self):
        """Test validation of invalid email formats."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                invalid_emails = [
                    "invalid",
                    "invalid@",
                    "@example.com",
                    "user@.com",
                    "",
                    "user@example",
                ]
                
                for email in invalid_emails:
                    assert invite_users_to_organization.validate_email(email) is False, f"Should fail for {email}"


class TestValidateAtlasCredentials:
    """Tests for validate_atlas_credentials function."""

    def test_validate_success(self):
        """Test successful credential validation."""
        import invite_users_to_organization
        
        # Set module-level vars to valid values
        invite_users_to_organization.PUBLIC_KEY = "test_key"
        invite_users_to_organization.PRIVATE_KEY = "test_key"
        invite_users_to_organization.ORGANIZATION_ID = "test_org"
        
        # Should not raise
        invite_users_to_organization.validate_atlas_credentials()

    def test_validate_missing_public_key(self):
        """Test validation fails with missing public key."""
        # Module-level vars are None by default, so just import and test
        import invite_users_to_organization
        
        # PUBLIC_KEY is None by default (set at runtime in main())
        # Set PRIVATE_KEY and ORGANIZATION_ID to test missing PUBLIC_KEY
        invite_users_to_organization.PUBLIC_KEY = None
        invite_users_to_organization.PRIVATE_KEY = "test_key"
        invite_users_to_organization.ORGANIZATION_ID = "test_org"
        
        with pytest.raises(ValueError) as excinfo:
            invite_users_to_organization.validate_atlas_credentials()
        assert "ATLAS_PUBLIC_KEY" in str(excinfo.value)


class TestMakeAtlasApiRequest:
    """Tests for make_atlas_api_request function."""

    def test_successful_request(self, mock_response):
        """Test successful API request."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200, {"data": "test"})
                    
                    result = invite_users_to_organization.make_atlas_api_request(
                        "GET", "http://test.com"
                    )
                    
                    assert result is not None
                    assert result.status_code == 200

    def test_failed_request(self):
        """Test failed API request returns None."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.side_effect = requests.exceptions.RequestException("Error")
                    
                    result = invite_users_to_organization.make_atlas_api_request(
                        "GET", "http://test.com"
                    )
                    
                    assert result is None


class TestInviteUsersToOrg:
    """Tests for invite_users_to_org function."""

    def test_invite_success(self, mock_response):
        """Test successful user invitations."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200)
                    
                    result = invite_users_to_organization.invite_users_to_org(
                        "org123", ["user@example.com"]
                    )
                    
                    assert result is True

    def test_invite_no_org_id(self):
        """Test handling of missing org ID."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                result = invite_users_to_organization.invite_users_to_org(
                    "", ["user@example.com"]
                )
                
                assert result is False

    def test_invite_empty_emails(self):
        """Test handling of empty email list."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                result = invite_users_to_organization.invite_users_to_org("org123", [])
                
                assert result is True  # No emails to invite is considered success

    def test_invite_invalid_email_skipped(self, mock_response):
        """Test that invalid emails are skipped."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200)
                    
                    # Include invalid email
                    result = invite_users_to_organization.invite_users_to_org(
                        "org123", ["invalid_email", "valid@example.com"]
                    )
                    
                    # One failed (invalid), one succeeded
                    assert result is False

    def test_invite_api_failure(self, mock_response):
        """Test handling of API failure during invitation."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.side_effect = requests.exceptions.RequestException("Error")
                    
                    result = invite_users_to_organization.invite_users_to_org(
                        "org123", ["user@example.com"]
                    )
                    
                    assert result is False

    def test_invite_multiple_users(self, mock_response):
        """Test inviting multiple users."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock get_existing_org_users to return empty set (no existing users)
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=set()
                    ):
                        mock_request.return_value = mock_response(201)
                        
                        emails = [
                            "user1@example.com",
                            "user2@example.com",
                            "user3@example.com",
                        ]
                        
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", emails
                        )
                        
                        assert result is True
                        # 3 invites (get_existing_org_users is mocked)
                        assert mock_request.call_count == 3


class TestMain:
    """Tests for main function."""

    def test_main_no_emails(self):
        """Test main function with no emails configured."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch.object(invite_users_to_organization, "EMAILS_TO_PROVISION", []):
                    result = invite_users_to_organization.main()
                    assert result == 0

    def test_main_cancelled(self):
        """Test main function when user cancels."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch.object(invite_users_to_organization, "EMAILS_TO_PROVISION", ["user@example.com"]):
                    with patch("builtins.input", return_value="n"):
                        result = invite_users_to_organization.main()
                        assert result == 0

    def test_main_confirmed_success(self, mock_response):
        """Test main function with successful execution."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch.object(invite_users_to_organization, "EMAILS_TO_PROVISION", ["user@example.com"]):
                    with patch("builtins.input", return_value="y"):
                        with patch("requests.request") as mock_request:
                            mock_request.return_value = mock_response(200)
                            
                            result = invite_users_to_organization.main()
                            assert result == 0

    def test_main_keyboard_interrupt(self):
        """Test main function handles KeyboardInterrupt."""
        import invite_users_to_organization
        
        # Set module-level vars to valid values
        invite_users_to_organization.PUBLIC_KEY = "test_key"
        invite_users_to_organization.PRIVATE_KEY = "test_key"
        invite_users_to_organization.ORGANIZATION_ID = "test_org"
        
        # Mock load_emails_from_csv to return test emails and load_dotenv to do nothing
        with patch.object(invite_users_to_organization, "load_emails_from_csv", return_value=["user@example.com"]):
            with patch.object(invite_users_to_organization, "load_dotenv"):
                with patch("builtins.input", side_effect=KeyboardInterrupt):
                    result = invite_users_to_organization.main()
                    assert result == 1

    def test_main_unexpected_error(self, mock_response):
        """Test main function handles unexpected errors."""
        import invite_users_to_organization
        
        # Set module-level vars to valid values
        invite_users_to_organization.PUBLIC_KEY = "test_key"
        invite_users_to_organization.PRIVATE_KEY = "test_key"
        invite_users_to_organization.ORGANIZATION_ID = "test_org"
        
        # Mock load_emails_from_csv to return test emails and load_dotenv to do nothing
        with patch.object(invite_users_to_organization, "load_emails_from_csv", return_value=["user@example.com"]):
            with patch.object(invite_users_to_organization, "load_dotenv"):
                with patch("builtins.input", return_value="y"):
                    with patch.object(
                        invite_users_to_organization,
                        "invite_users_to_org",
                        side_effect=Exception("Unexpected")
                    ):
                        result = invite_users_to_organization.main()
                        assert result == 1


class TestModuleInitialization:
    """Regression tests that verify load_dotenv() is called at module level.

    These tests ensure that load_dotenv() is called during module import,
    not just in main(), preventing the authentication bug where environment
    variables weren't loaded before module-level variables were set.
    """

    def test_load_dotenv_called_at_module_level(self):
        """
        Test that load_dotenv() is called at module level, not just in main().
        This ensures environment variables are loaded before module-level variables are set.
        """
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_public_key",
            "ATLAS_PRIVATE_KEY": "test_private_key",
            "ATLAS_ORG_ID": "test_org_id",
        }, clear=True):
            # Temporarily disable the autouse mock_load_dotenv fixture
            # by patching dotenv.load_dotenv before module import
            import importlib

            if "invite_users_to_organization" in sys.modules:
                del sys.modules["invite_users_to_organization"]

            # Patch dotenv.load_dotenv BEFORE importing the module
            # When the module does "from dotenv import load_dotenv", it will get our patched version
            with patch("dotenv.load_dotenv", wraps=lambda: None) as mock_load:
                # Import should trigger load_dotenv() at module level
                import invite_users_to_organization

                # Verify load_dotenv was called during import
                assert (
                    mock_load.called
                ), "load_dotenv() should be called at module level during import"
                
                # Verify module-level variables are set from environment
                assert invite_users_to_organization.PUBLIC_KEY == "test_public_key"
                assert invite_users_to_organization.PRIVATE_KEY == "test_private_key"
                assert invite_users_to_organization.ORGANIZATION_ID == "test_org_id"


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limit_delay_constant_default(self):
        """Test that RATE_LIMIT_DELAY_SECONDS has correct default value."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                assert invite_users_to_organization.RATE_LIMIT_DELAY_SECONDS == 6.0

    def test_rate_limit_delay_constant_from_env(self):
        """Test that RATE_LIMIT_DELAY_SECONDS can be configured via environment variable."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org",
            "RATE_LIMIT_DELAY_SECONDS": "10.5"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                assert invite_users_to_organization.RATE_LIMIT_DELAY_SECONDS == 10.5

    def test_delay_applied_between_requests(self, mock_response):
        """Test that delay is applied between invitation requests."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200)
                    with patch("time.sleep") as mock_sleep:
                        emails = ["user1@example.com", "user2@example.com", "user3@example.com"]
                        
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", emails
                        )
                        
                        # Should sleep 2 times (between 3 emails, skip last)
                        assert mock_sleep.call_count == 2
                        # Each sleep should be the rate limit delay
                        for call in mock_sleep.call_args_list:
                            assert call[0][0] == 6.0
                        assert result is True

    def test_no_delay_after_last_email(self, mock_response):
        """Test that delay is not applied after the last email."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200)
                    with patch("time.sleep") as mock_sleep:
                        # Single email - no delay should be applied
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["user1@example.com"]
                        )
                        
                        assert mock_sleep.call_count == 0
                        assert result is True

    def test_429_response_with_exponential_backoff(self, mock_response):
        """Test that 429 responses trigger exponential backoff retries."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # First two attempts return 429, third succeeds
                    mock_request.side_effect = [
                        mock_response(429),
                        mock_response(429),
                        mock_response(200),
                    ]
                    with patch("time.sleep") as mock_sleep:
                        result = invite_users_to_organization.make_atlas_api_request(
                            "POST", "http://test.com"
                        )
                        
                        # Should have retried twice with exponential backoff
                        assert mock_request.call_count == 3
                        assert mock_sleep.call_count == 2
                        # First retry: 1 second, second retry: 2 seconds
                        assert mock_sleep.call_args_list[0][0][0] == 1
                        assert mock_sleep.call_args_list[1][0][0] == 2
                        assert result is not None
                        assert result.status_code == 200

    def test_429_response_with_retry_after_header(self, mock_response):
        """Test that Retry-After header is respected when present."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Create response with Retry-After header
                    response_429 = mock_response(429)
                    response_429.headers = {"Retry-After": "5"}
                    response_200 = mock_response(200)
                    
                    mock_request.side_effect = [response_429, response_200]
                    with patch("time.sleep") as mock_sleep:
                        result = invite_users_to_organization.make_atlas_api_request(
                            "POST", "http://test.com"
                        )
                        
                        # Should have retried once with Retry-After delay
                        assert mock_request.call_count == 2
                        assert mock_sleep.call_count == 1
                        # Should use Retry-After value (5 seconds) instead of exponential backoff
                        assert mock_sleep.call_args_list[0][0][0] == 5
                        assert result is not None
                        assert result.status_code == 200

    def test_429_response_max_retries_exceeded(self, mock_response):
        """Test that request fails after max retries are exhausted."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # All attempts return 429
                    mock_request.return_value = mock_response(429)
                    with patch("time.sleep") as mock_sleep:
                        result = invite_users_to_organization.make_atlas_api_request(
                            "POST", "http://test.com"
                        )
                        
                        # Should have tried 4 times (initial + 3 retries)
                        assert mock_request.call_count == 4
                        assert mock_sleep.call_count == 3
                        # Exponential backoff: 1s, 2s, 4s
                        assert mock_sleep.call_args_list[0][0][0] == 1
                        assert mock_sleep.call_args_list[1][0][0] == 2
                        assert mock_sleep.call_args_list[2][0][0] == 4
                        assert result is None

    def test_429_in_exception_response(self, mock_response):
        """Test that 429 in exception response triggers retry."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # First attempt raises exception with 429 response, second succeeds
                    error = requests.exceptions.HTTPError("Rate limited")
                    error.response = mock_response(429)
                    mock_request.side_effect = [error, mock_response(200)]
                    
                    with patch("time.sleep") as mock_sleep:
                        result = invite_users_to_organization.make_atlas_api_request(
                            "POST", "http://test.com"
                        )
                        
                        # Should have retried once
                        assert mock_request.call_count == 2
                        assert mock_sleep.call_count == 1
                        assert mock_sleep.call_args_list[0][0][0] == 1
                        assert result is not None
                        assert result.status_code == 200

    def test_non_429_error_no_retry(self):
        """Test that non-429 errors don't trigger retries."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.side_effect = requests.exceptions.RequestException("Connection error")
                    
                    with patch("time.sleep") as mock_sleep:
                        result = invite_users_to_organization.make_atlas_api_request(
                            "POST", "http://test.com"
                        )
                        
                        # Should not retry for non-429 errors
                        assert mock_request.call_count == 1
                        assert mock_sleep.call_count == 0
                        assert result is None

    def test_rate_limit_delay_in_invite_loop(self, mock_response):
        """Test that rate limit delay is applied in invite_users_to_org loop."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org",
            "RATE_LIMIT_DELAY_SECONDS": "3.5"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(200)
                    with patch("time.sleep") as mock_sleep:
                        emails = ["user1@example.com", "user2@example.com"]
                        
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", emails
                        )
                        
                        # Should use the configured delay from environment
                        assert mock_sleep.call_count == 1
                        assert mock_sleep.call_args_list[0][0][0] == 3.5
                        assert result is True


class Test409ConflictHandling:
    """Tests for handling 409 Conflict errors (invitation already exists)."""

    def test_409_conflict_handled_gracefully(self, mock_response):
        """Test that 409 Conflict errors are handled gracefully."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Return 409 Conflict
                    mock_request.return_value = mock_response(409)
                    
                    result = invite_users_to_organization.make_atlas_api_request(
                        "POST", "http://test.com"
                    )
                    
                    # Should return the response, not None
                    assert result is not None
                    assert result.status_code == 409

    def test_409_conflict_in_invite_treated_as_success(self, mock_response):
        """Test that 409 Conflict in invite_users_to_org is treated as success."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock get_existing_org_users to return empty set
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=set()
                    ):
                        mock_request.return_value = mock_response(409)
                        
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["user@example.com"]
                        )
                        
                        # Should be treated as success
                        assert result is True
                        # 1 invite (get_existing_org_users is mocked)
                        assert mock_request.call_count == 1

    def test_409_conflict_in_exception_handler(self, mock_response):
        """Test that 409 Conflict in exception handler is handled correctly."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Simulate real scenario: response has 409, raise_for_status raises HTTPError
                    response_409 = mock_response(409)
                    error = requests.exceptions.HTTPError("409 Client Error: Conflict")
                    error.response = response_409
                    response_409.raise_for_status.side_effect = error
                    mock_request.return_value = response_409
                    
                    result = invite_users_to_organization.make_atlas_api_request(
                        "POST", "http://test.com"
                    )
                    
                    # Should return the response BEFORE raise_for_status() is called
                    assert result is not None
                    assert result.status_code == 409
                    # raise_for_status should not have been called since we return early
                    assert not response_409.raise_for_status.called

    def test_mixed_409_and_success_invitations(self, mock_response):
        """Test handling of mixed 409 and successful invitations."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock get_existing_org_users to return empty set
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=set()
                    ):
                        # First returns 409, second succeeds
                        mock_request.side_effect = [
                            mock_response(409),
                            mock_response(200),
                        ]
                        
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["existing@example.com", "new@example.com"]
                        )
                        
                        # Both should be treated as success
                        assert result is True
                        # 2 invites (get_existing_org_users is mocked)
                        assert mock_request.call_count == 2

    def test_409_conflict_logs_warning_not_error(self, mock_response, caplog):
        """Test that 409 Conflict logs a warning, not an error."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.return_value = mock_response(409)
                    
                    invite_users_to_organization.invite_users_to_org(
                        "org123", ["user@example.com"]
                    )
                    
                    # Check that warning was logged, not error
                    warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
                    error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
                    
                    assert any("already exists" in r.message.lower() for r in warning_logs)
                    assert not any("failed to invite" in r.message.lower() for r in error_logs)


class TestGetExistingOrgUsers:
    """Tests for get_existing_org_users function."""

    def test_get_existing_users_success(self, mock_response):
        """Test successfully fetching existing users."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock response with users
                    users_data = {
                        "results": [
                            {"username": "user1@example.com"},
                            {"username": "user2@example.com"},
                        ]
                    }
                    mock_request.return_value = mock_response(200, users_data)
                    
                    result = invite_users_to_organization.get_existing_org_users("org123")
                    
                    assert isinstance(result, set)
                    assert len(result) == 2
                    assert "user1@example.com" in result
                    assert "user2@example.com" in result

    def test_get_existing_users_case_insensitive(self, mock_response):
        """Test that email comparison is case-insensitive."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    users_data = {
                        "results": [
                            {"username": "User1@Example.com"},
                        ]
                    }
                    mock_request.return_value = mock_response(200, users_data)
                    
                    result = invite_users_to_organization.get_existing_org_users("org123")
                    
                    # Should store lowercase
                    assert "user1@example.com" in result
                    assert "User1@Example.com" not in result

    def test_get_existing_users_pagination(self, mock_response):
        """Test handling paginated responses."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # First page
                    page1_data = {
                        "results": [{"username": "user1@example.com"}],
                        "links": [{"rel": "next", "href": "http://next"}]
                    }
                    # Second page
                    page2_data = {
                        "results": [{"username": "user2@example.com"}],
                        "links": []
                    }
                    mock_request.side_effect = [
                        mock_response(200, page1_data),
                        mock_response(200, page2_data),
                    ]
                    
                    result = invite_users_to_organization.get_existing_org_users("org123")
                    
                    assert len(result) == 2
                    assert "user1@example.com" in result
                    assert "user2@example.com" in result
                    assert mock_request.call_count == 2

    def test_get_existing_users_api_failure(self, mock_response):
        """Test graceful handling of API failure."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    mock_request.side_effect = requests.exceptions.RequestException("Error")
                    
                    result = invite_users_to_organization.get_existing_org_users("org123")
                    
                    # Should return empty set on failure (fail-safe)
                    assert isinstance(result, set)
                    assert len(result) == 0

    def test_get_existing_users_no_org_id(self):
        """Test handling of missing org ID."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                result = invite_users_to_organization.get_existing_org_users("")
                
                assert isinstance(result, set)
                assert len(result) == 0

    def test_get_existing_users_list_response(self, mock_response):
        """Test handling of list response (non-paginated)."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Some APIs return list directly
                    users_list = [
                        {"username": "user1@example.com"},
                        {"username": "user2@example.com"},
                    ]
                    mock_response_obj = mock_response(200, users_list)
                    # Mock json() to return list directly
                    mock_response_obj.json.return_value = users_list
                    mock_request.return_value = mock_response_obj
                    
                    result = invite_users_to_organization.get_existing_org_users("org123")
                    
                    assert len(result) == 2
                    assert "user1@example.com" in result
                    assert "user2@example.com" in result


class TestSkipExistingUsers:
    """Tests for skipping existing users in invitation flow."""

    def test_skip_existing_user(self, mock_response):
        """Test that existing users are skipped."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock get_existing_org_users to return existing user
                    existing_users = {"existing@example.com"}
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=existing_users
                    ):
                        # Mock successful invite response for new user
                        mock_request.return_value = mock_response(200)
                        
                        # Should not make invite request for existing user
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["existing@example.com", "new@example.com"]
                        )
                        
                        # Should only invite the new user (not the existing one)
                        # mock_request is called once for the invite (get_existing_org_users is mocked)
                        assert mock_request.call_count == 1
                        assert result is True

    def test_skip_existing_user_case_insensitive(self, mock_response):
        """Test that existing user check is case-insensitive."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Existing user stored as lowercase
                    existing_users = {"user@example.com"}
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=existing_users
                    ):
                        # Try to invite with different case
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["User@Example.com"]
                        )
                        
                        # Should skip (case-insensitive match)
                        assert mock_request.call_count == 0
                        assert result is True

    def test_skip_existing_user_logs_info(self, mock_response, caplog):
        """Test that skipping existing user logs appropriate message."""
        with caplog.at_level(logging.INFO):
            with patch.dict(os.environ, {
                "ATLAS_PUBLIC_KEY": "test_key",
                "ATLAS_PRIVATE_KEY": "test_key",
                "ATLAS_ORG_ID": "test_org"
            }):
                with patch("builtins.open", mock_open(read_data="")):
                    import importlib
                    import invite_users_to_organization
                    importlib.reload(invite_users_to_organization)
                    
                    with patch("requests.request") as mock_request:
                        existing_users = {"existing@example.com"}
                        with patch.object(
                            invite_users_to_organization,
                            "get_existing_org_users",
                            return_value=existing_users
                        ):
                            invite_users_to_organization.invite_users_to_org(
                                "org123", ["existing@example.com"]
                            )
                            
                            # Check that info message was logged
                            all_logs = [r for r in caplog.records]
                            # Check for the skip message in any log level
                            skip_messages = [
                                r for r in all_logs 
                                if "already exists" in r.message.lower() or "skipping" in r.message.lower()
                            ]
                            assert len(skip_messages) > 0, f"No skip message found. All logs: {[(r.levelname, r.message) for r in all_logs]}"

    def test_continue_on_get_users_failure(self, mock_response):
        """Test that invitation continues if fetching existing users fails."""
        with patch.dict(os.environ, {
            "ATLAS_PUBLIC_KEY": "test_key",
            "ATLAS_PRIVATE_KEY": "test_key",
            "ATLAS_ORG_ID": "test_org"
        }):
            with patch("builtins.open", mock_open(read_data="")):
                import importlib
                import invite_users_to_organization
                importlib.reload(invite_users_to_organization)
                
                with patch("requests.request") as mock_request:
                    # Mock get_existing_org_users to fail
                    with patch.object(
                        invite_users_to_organization,
                        "get_existing_org_users",
                        return_value=set()  # Empty set on failure
                    ):
                        # Should still proceed with invitation
                        mock_request.return_value = mock_response(200)
                        result = invite_users_to_organization.invite_users_to_org(
                            "org123", ["user@example.com"]
                        )
                        
                        # Should have attempted invitation
                        assert mock_request.call_count >= 1
                        assert result is True

