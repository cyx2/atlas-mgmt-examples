"""
Invite Users To Organization

This script manages user invitations to MongoDB Atlas organizations, allowing
bulk invitation of users with specified roles and permissions.

Prerequisites:
    - Python 3.6+
    - Required packages: requests, python-dotenv
    - Valid Atlas API credentials in .env file

Environment Variables:
    ATLAS_PUBLIC_KEY: MongoDB Atlas API Public Key
    ATLAS_PRIVATE_KEY: MongoDB Atlas API Private Key
    ATLAS_ORG_ID: Atlas Organization ID
    ATLAS_API_BASE_URL: (Optional) Atlas API Base URL

Usage:
    python invite_users_to_organization.py

Note:
    Modify EMAILS_TO_PROVISION list in the script to specify target users.
"""

import csv
import logging
import os
from typing import List, Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/invite_users_to_org.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("invite_users_to_org")

# Load environment variables
load_dotenv()

# --- Configuration Constants ---
ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)
PUBLIC_KEY: Optional[str] = os.getenv("ATLAS_PUBLIC_KEY")
PRIVATE_KEY: Optional[str] = os.getenv("ATLAS_PRIVATE_KEY")
ORGANIZATION_ID: Optional[str] = os.getenv("ATLAS_ORG_ID")


# Load email addresses from CSV file
def load_emails_from_csv(csv_file_path: str) -> List[str]:
    """
    Load email addresses from a CSV file.

    Args:
        csv_file_path: Path to the CSV file containing email addresses

    Returns:
        List of email addresses
    """
    emails = []
    try:
        with open(csv_file_path, "r", newline="") as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row and row[0].strip():  # Skip empty rows
                    emails.append(row[0].strip())
        logger.info(f"Loaded {len(emails)} email addresses from {csv_file_path}")
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_file_path}")
        raise
    except Exception as e:
        logger.error(f"Error reading CSV file {csv_file_path}: {str(e)}")
        raise

    return emails


# Email list will be loaded at runtime in main()
EMAILS_TO_PROVISION: List[str] = []


# Validate required credentials
def validate_atlas_credentials():
    """Validate that all required Atlas environment variables are set."""
    missing_vars = []

    if not PUBLIC_KEY:
        missing_vars.append("ATLAS_PUBLIC_KEY")
    if not PRIVATE_KEY:
        missing_vars.append("ATLAS_PRIVATE_KEY")
    if not ORGANIZATION_ID:
        missing_vars.append("ATLAS_ORG_ID")

    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
        logger.error("Please ensure all required variables are set in your .env file")
        raise ValueError(
            f"Missing required Atlas API credentials: {', '.join(missing_vars)}"
        )


def validate_email(email: str) -> bool:
    """
    Basic email validation.

    Args:
        email: Email address to validate

    Returns:
        True if email appears valid, False otherwise
    """
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def make_atlas_api_request(
    method: str, url: str, **kwargs
) -> Optional[requests.Response]:
    """
    Make an Atlas API request with proper error handling.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        url: Full URL for the request
        **kwargs: Additional arguments to pass to requests

    Returns:
        Response object if successful, None if failed
    """
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {method} {url} - {str(e)}")
        return None


def invite_users_to_org(org_id: str, emails: List[str]) -> bool:
    """
    Invite users to an Atlas organization.

    Args:
        org_id: The ID of the Atlas organization
        emails: List of email addresses to invite

    Returns:
        True if all invitations were successful, False otherwise
    """
    if not org_id:
        logger.error("Organization ID is required but not provided")
        return False

    if not emails:
        logger.warning("No email addresses provided for invitation")
        return True

    logger.info(f"Starting invitation process for {len(emails)} users")

    url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/invites"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    successful_invites = 0
    failed_invites = 0

    for email in emails:
        # Validate email format
        if not validate_email(email):
            logger.error(f"Invalid email format: {email}")
            failed_invites += 1
            continue

        logger.info(f"Inviting user: {email}")

        payload = {"roles": ["ORG_GROUP_CREATOR"], "username": email}

        response = make_atlas_api_request(
            "POST", url, json=payload, headers=headers, auth=auth
        )

        if response and response.status_code in [200, 201]:
            logger.info(f"Successfully invited {email} to the organization")
            successful_invites += 1
        else:
            logger.error(f"Failed to invite {email}")
            failed_invites += 1

    logger.info(
        f"Invitation process completed. Successful: {successful_invites}, Failed: {failed_invites}"
    )
    return failed_invites == 0


def main():
    """Main function with comprehensive error handling."""
    global EMAILS_TO_PROVISION
    try:
        logger.info("Starting MongoDB Atlas user invitation tool")

        # Validate credentials at runtime
        validate_atlas_credentials()

        # Load emails from CSV at runtime
        try:
            EMAILS_TO_PROVISION = load_emails_from_csv("invitees.csv")
        except FileNotFoundError:
            logger.error("invitees.csv not found. Please create the file with email addresses.")
            print("Error: invitees.csv not found. Please create the file with email addresses.")
            return 1

        if not EMAILS_TO_PROVISION:
            logger.warning("No emails configured for invitation")
            print("No emails configured in EMAILS_TO_PROVISION list.")
            return 0

        print(
            f"About to invite {len(EMAILS_TO_PROVISION)} users to organization {ORGANIZATION_ID}"
        )
        print("Users to invite:")
        for email in EMAILS_TO_PROVISION:
            print(f"  - {email}")

        confirm = input("\nProceed with invitations? (y/N): ").lower().strip()
        if confirm != "y":
            logger.info("Operation cancelled by user")
            print("Operation cancelled.")
            return 0

        success = invite_users_to_org(ORGANIZATION_ID, EMAILS_TO_PROVISION)

        if success:
            logger.info("All invitations completed successfully")
            return 0
        else:
            logger.error("Some invitations failed")
            return 1

    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        print("\nOperation interrupted.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
