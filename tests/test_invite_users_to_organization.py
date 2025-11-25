"""
Tests for invite_users_to_organization.py

This module tests the user invitation functionality including:
- Email loading from CSV
- Email validation
- API requests
- User invitation process
"""

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

