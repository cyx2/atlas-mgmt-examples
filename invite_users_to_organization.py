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
import time
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
PUBLIC_KEY = os.getenv("ATLAS_PUBLIC_KEY")
PRIVATE_KEY = os.getenv("ATLAS_PRIVATE_KEY")
ORGANIZATION_ID = os.getenv("ATLAS_ORG_ID")
# Rate limit: 10 invitations per minute for the invite endpoint
RATE_LIMIT_DELAY_SECONDS = float(os.getenv("RATE_LIMIT_DELAY_SECONDS", "6.0"))


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
        with open(csv_file_path, "r", encoding="utf-8-sig", newline="") as csvfile:
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
    Make an Atlas API request with proper error handling and rate limit retry logic.

    Args:
        method: HTTP method (GET, POST, DELETE, etc.)
        url: Full URL for the request
        **kwargs: Additional arguments to pass to requests

    Returns:
        Response object if successful, None if failed
    """
    max_retries = 3
    backoff_delays = [1, 2, 4]  # Exponential backoff delays in seconds

    for attempt in range(max_retries + 1):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)

            # Handle 409 Conflict (invitation already exists) - return response for caller to handle
            # Check this BEFORE raise_for_status() to avoid exception
            if response.status_code == 409:
                logger.debug(
                    f"Detected 409 Conflict response for {method} {url}, returning response"
                )
                return response

            # Handle rate limiting (429 Too Many Requests)
            if response.status_code == 429:
                if attempt < max_retries:
                    # Check for Retry-After header, otherwise use exponential backoff
                    if "Retry-After" in response.headers:
                        wait_time = int(response.headers.get("Retry-After"))
                        logger.warning(
                            f"Rate limit exceeded (429). Retry-After header indicates waiting {wait_time} seconds "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                    else:
                        wait_time = backoff_delays[attempt]
                        logger.warning(
                            f"Rate limit exceeded (429). Retrying in {wait_time} seconds "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"Rate limit exceeded (429) after {max_retries + 1} attempts. "
                        f"Request failed: {method} {url}"
                    )
                    return None

            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            # HTTPError has response attribute - check for 409 or 429
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 409:
                    return e.response
                elif e.response.status_code == 429:
                    # Only retry on 429 errors
                    if attempt < max_retries:
                        wait_time = backoff_delays[attempt]
                        logger.warning(
                            f"Rate limit exceeded (429). Retrying in {wait_time} seconds "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(wait_time)
                        continue
            logger.error(f"API request failed: {method} {url} - {str(e)}")
            return None
        except requests.exceptions.RequestException as e:
            # Handle other request exceptions (connection errors, etc.)
            # Check if exception has response attribute (some exceptions do)
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 409:
                    return e.response
                elif e.response.status_code == 429:
                    # Only retry on 429 errors
                    if attempt < max_retries:
                        wait_time = backoff_delays[attempt]
                        logger.warning(
                            f"Rate limit exceeded (429). Retrying in {wait_time} seconds "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(wait_time)
                        continue

            logger.error(f"API request failed: {method} {url} - {str(e)}")
            return None

    return None


def get_existing_org_users(org_id: str) -> set:
    """
    Get all existing users in an Atlas organization (including pending invitations).

    Args:
        org_id: The ID of the Atlas organization

    Returns:
        Set of email addresses (usernames) of existing users
    """
    if not org_id:
        logger.warning("Organization ID is required to fetch existing users")
        return set()

    url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/users"
    headers = {
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    existing_users = set()
    page = 1
    max_pages = 100  # Safety limit

    while page <= max_pages:
        # Add pagination parameters
        params = {"pageNum": page, "itemsPerPage": 500}
        response = make_atlas_api_request(
            "GET", url, headers=headers, auth=auth, params=params
        )

        if not response:
            if page == 1:
                # If first page fails, log warning but return empty set (fail-safe)
                logger.warning(
                    "Failed to fetch existing users from organization. "
                    "Will proceed with invitations (may result in duplicates)."
                )
            break

        try:
            data = response.json()
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse users response: {str(e)}")
            break

        # Handle list response (non-paginated)
        if isinstance(data, list):
            for user in data:
                username = user.get("username")
                if username:
                    existing_users.add(username.lower())  # Case-insensitive comparison
            break

        # Handle dict response with results key (paginated)
        if "results" in data and data["results"]:
            for user in data["results"]:
                username = user.get("username")
                if username:
                    existing_users.add(username.lower())  # Case-insensitive comparison
        else:
            break

        # Check for next page
        links = data.get("links", [])
        has_next = any(link.get("rel") == "next" for link in links)
        if not has_next:
            break

        page += 1

    logger.info(f"Found {len(existing_users)} existing users in organization")
    return existing_users


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

    # Fetch existing users once at the start
    existing_users = get_existing_org_users(org_id)

    url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/invites"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    successful_invites = 0
    failed_invites = 0
    skipped_existing = 0

    for email in emails:
        # Validate email format
        if not validate_email(email):
            logger.error(f"Invalid email format: {email}")
            failed_invites += 1
            continue

        # Check if user already exists (case-insensitive comparison)
        if email.lower() in existing_users:
            logger.info(
                f"User {email} already exists in the organization. Skipping invitation."
            )
            successful_invites += 1  # Treat as success since user already exists
            skipped_existing += 1
            continue

        logger.info(f"Inviting user: {email}")

        payload = {"roles": ["ORG_GROUP_CREATOR"], "username": email}

        response = make_atlas_api_request(
            "POST", url, json=payload, headers=headers, auth=auth
        )

        if response is None:
            logger.error(f"Failed to invite {email} - API request returned None")
            failed_invites += 1
        elif response.status_code in [200, 201]:
            logger.info(f"Successfully invited {email} to the organization")
            successful_invites += 1
        elif response.status_code == 409:
            logger.warning(
                f"Invitation already exists for {email} (409 Conflict). Skipping."
            )
            successful_invites += 1  # Treat as success since invitation already exists
        else:
            logger.error(
                f"Failed to invite {email} - Unexpected status code: {response.status_code}"
            )
            failed_invites += 1

        # Add delay between requests to respect rate limits (10 invitations per minute)
        # Skip delay after the last email to avoid unnecessary wait
        if email != emails[-1]:
            logger.debug(
                f"Waiting {RATE_LIMIT_DELAY_SECONDS} seconds before next invitation..."
            )
            time.sleep(RATE_LIMIT_DELAY_SECONDS)

    logger.info(
        f"Invitation process completed. Successful: {successful_invites}, "
        f"Failed: {failed_invites}, Skipped (already exists): {skipped_existing}"
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
            logger.error(
                "invitees.csv not found. Please create the file with email addresses."
            )
            print(
                "Error: invitees.csv not found. Please create the file with email addresses."
            )
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
