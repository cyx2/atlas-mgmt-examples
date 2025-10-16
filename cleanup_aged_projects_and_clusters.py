"""
Cleanup Aged Projects and Clusters

This script retrieves all projects within a MongoDB Atlas organization and performs cleanup
operations on projects older than 90 days by:
1. Deleting all database users in those projects
2. Removing all Atlas users' access from those projects
3. Deleting ALL clusters in projects older than 120 days
4. Deleting ALL pending organization invitations (if any old projects are found)

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
    python cleanup_aged_projects_and_clusters.py

    The script will:
    1. Validate Atlas API credentials
    2. Show warning about destructive operations
    3. Request user confirmation with specific phrase
    4. Process all projects in the organization
    5. Clean up users from projects older than 90 days
    6. Report statistics on completion

    Example:
        $ python cleanup_aged_projects_and_clusters.py
        ⚠️  WARNING: This script will perform DESTRUCTIVE operations!
        Organization ID: 507f1f77bcf86cd799439011
        Projects older than 90 days will have:
          - All database users deleted
          - All Atlas users removed from projects
        Projects older than 120 days will also have:
          - All clusters deleted

        Type 'REAP PROJECTS OLDER THAN 90 DAYS' to confirm: REAP PROJECTS OLDER THAN 90 DAYS

Safety Warning:
    This script performs DESTRUCTIVE operations. Use with extreme caution.
    Test thoroughly in non-production environments first.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration Constants ---
ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)
# Use current UTC time for consistent comparison with API's UTC timestamps
CURRENT_DATE_UTC = datetime.now(timezone.utc)
USER_DELETION_THRESHOLD = 90  # Delete users from projects older than this many days
CLUSTER_DELETION_THRESHOLD = 120  # Delete clusters in projects older than 120 days

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/reaper.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("atlas_reaper")
# --- Helper Functions ---


def validate_atlas_credentials():
    """Validate that all required Atlas environment variables are set."""
    missing_vars = []

    if not os.getenv("ATLAS_PUBLIC_KEY"):
        missing_vars.append("ATLAS_PUBLIC_KEY")
    if not os.getenv("ATLAS_PRIVATE_KEY"):
        missing_vars.append("ATLAS_PRIVATE_KEY")
    if not os.getenv("ATLAS_ORG_ID"):
        missing_vars.append("ATLAS_ORG_ID")

    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
        logger.error("Please ensure all required variables are set in your .env file")
        raise ValueError(
            f"Missing required Atlas API credentials: {', '.join(missing_vars)}"
        )

    logger.info("Atlas API credentials validated successfully")


def get_env_variable(var_name: str) -> str:
    """
    Get an environment variable with validation.

    Args:
        var_name: Name of the environment variable

    Returns:
        Value of the environment variable

    Raises:
        ValueError: If environment variable is not set
    """
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Environment variable {var_name} not set.")
    return value


def make_atlas_api_request(method, url, auth, params=None, json_data=None):
    """Makes an Atlas API request and handles potential errors."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    }

    try:
        response = requests.request(
            method,
            url,
            auth=auth,
            params=params,
            json=json_data,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        if response.status_code == 204:  # No content, like for successful deletions
            return None
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - {response.text}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error occurred: {req_err}")
    except ValueError as json_err:  # Includes JSONDecodeError
        logger.error(f"JSON decode error: {json_err} - Response was: {response.text}")
    return None


def get_all_paginated_items(url, auth, item_key="results", max_pages=100):
    """Retrieves all items from a paginated Atlas API endpoint."""
    all_items = []
    params = {"itemsPerPage": 500}  # Max items per page
    current_page = 1
    while True:
        params["pageNum"] = current_page
        data = make_atlas_api_request("GET", url, auth, params=params)

        # Check if API request failed
        if data is None:
            logger.error(f"API request failed for {url} (page {current_page})")
            break

        if not data or item_key not in data or not data[item_key]:
            break

        all_items.extend(data[item_key])
        # Check if there are more pages (Atlas uses a "links" array with "next" relation)
        if not any(link.get("rel") == "next" for link in data.get("links", [])):
            break
        current_page += 1
        if current_page > max_pages:  # Safety break
            logger.warning(
                f"Reached max_pages ({max_pages}) limit for {url}. Not all items might be fetched."
            )
            break
    return all_items


def get_atlas_projects(org_id, auth):
    """Retrieves all projects for a given organization ID."""
    url = f"{ATLAS_API_BASE_URL}/groups"
    logger.info(f"Fetching all projects for org: {org_id}...")
    projects = get_all_paginated_items(url, auth)
    logger.info(f"Found {len(projects)} projects.")
    return projects


def get_atlas_database_users(project_id, auth):
    """Retrieves all database users for a given project ID."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/databaseUsers"
    # print(f"  Fetching database users for project: {project_id}...")
    users = get_all_paginated_items(url, auth)
    # print(f"  Found {len(users)} database users.")
    return users


def delete_atlas_database_user(project_id, username, auth, db_name="admin"):
    """Deletes a database user from a project."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/databaseUsers/{db_name}/{username}"
    logger.info(
        f"  Attempting to delete database user: {username} from project {project_id}..."
    )
    result = make_atlas_api_request("DELETE", url, auth)
    if result is None:  # Successful deletion returns 204 No Content
        logger.info(f"  Successfully deleted database user: {username}")
        return True
    else:
        logger.error(
            f"  Failed to delete database user: {username}. Response: {result}"
        )
        return False


def get_atlas_project_users(project_id, auth):
    """Retrieves all Atlas users associated with a given project ID."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/users"
    # print(f"  Fetching Atlas users for project: {project_id}...")
    users = get_all_paginated_items(url, auth)
    # print(f"  Found {len(users)} Atlas users with access to project.")
    return users


def delete_atlas_project_user(project_id, user_id, auth):
    """Removes an Atlas user's access from a specific project."""
    # Note: The API for removing a user from a project is by removing them from ALL roles in that project.
    # The typical way is to remove the user from the project itself, which revokes all their roles within that project.
    # If this direct endpoint is not available for "removing from project", one might need to update the user's roles
    # or use a different approach if the API specifically offers project-level user removal.
    # For v2, this is the correct endpoint to remove a user's assignment to a project.
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/users/{user_id}"
    logger.info(
        f"  Attempting to remove Atlas user ID: {user_id} from project {project_id}..."
    )
    result = make_atlas_api_request("DELETE", url, auth)
    if result is None:  # Successful removal returns 204 No Content
        logger.info(
            f"  Successfully removed Atlas user ID: {user_id} from project {project_id}."
        )
        return True
    else:
        logger.error(f"  Failed to remove Atlas user ID: {user_id}. Response: {result}")
        return False


def get_atlas_clusters(project_id, auth):
    """Retrieves all clusters for a given project ID."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters"
    clusters = get_all_paginated_items(url, auth)
    return clusters


def delete_atlas_cluster(project_id, cluster_name, auth):
    """Deletes a cluster from a project."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
    logger.info(
        f"  Attempting to delete cluster: {cluster_name} from project {project_id}..."
    )
    result = make_atlas_api_request("DELETE", url, auth)
    if result is None:  # Successful deletion returns 204 No Content
        logger.info(f"  Successfully initiated deletion of cluster: {cluster_name}")
        return True
    else:
        logger.error(f"  Failed to delete cluster: {cluster_name}. Response: {result}")
        return False


def get_atlas_org_invitations(org_id, auth):
    """
    Retrieves all pending invitations for the organization.
    Since project-level invitation endpoints are deprecated, we use org-level invitations
    and filter by project during processing.
    """
    url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/invitations"
    # print(f"  Fetching organization invitations for org: {org_id}...")
    invitations = get_all_paginated_items(url, auth)
    # print(f"  Found {len(invitations)} pending invitations at org level.")
    return invitations


def delete_invitations_for_old_projects(org_id, org_invitations, old_project_ids, auth):
    """
    Deletes ALL pending organization invitations when old projects are found.
    This ensures that users with pending invitations are properly cleaned up
    during the reaper process.

    Args:
        org_id: Organization ID
        org_invitations: List of all organization invitations
        old_project_ids: Set of project IDs that are older than 90 days
        auth: Authentication object

    Returns:
        Tuple of (successful_deletions, failed_deletions)
    """
    successful = 0
    failed = 0

    if not org_invitations:
        logger.info("  No pending invitations found at organization level")
        return successful, failed

    if not old_project_ids:
        logger.info("  No old projects found, skipping invitation cleanup")
        return successful, failed

    logger.info(
        f"  Found old projects requiring cleanup. Deleting ALL {len(org_invitations)} pending organization invitations..."
    )

    for invitation in org_invitations:
        invitation_id = invitation.get("id")
        username = invitation.get("username", "Unknown")

        if invitation_id:
            logger.info(
                f"  Deleting invitation for user: {username} (ID: {invitation_id})"
            )
            if delete_atlas_org_invitation(org_id, invitation_id, auth):
                successful += 1
            else:
                failed += 1
        else:
            logger.warning(
                f"  Skipping invitation with missing ID for user: {username}"
            )
            failed += 1

    logger.info(
        f"  Invitation cleanup completed: {successful} successful, {failed} failed"
    )
    return successful, failed


def delete_atlas_org_invitation(org_id, invitation_id, auth):
    """
    Deletes a pending invitation from the organization.
    Using the organization-level endpoint since project-level endpoints are deprecated.
    """
    url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/invitations/{invitation_id}"
    logger.info(
        f"  Attempting to delete invitation ID: {invitation_id} from organization..."
    )
    result = make_atlas_api_request("DELETE", url, auth)
    if result is None:  # Successful deletion returns 204 No Content
        logger.info(f"  Successfully deleted invitation ID: {invitation_id}")
        return True
    else:
        logger.error(
            f"  Failed to delete invitation ID: {invitation_id}. Response: {result}"
        )
        return False


# --- Main Script Logic ---
def main():
    """Main function with comprehensive error handling and user confirmation."""
    try:
        logger.info("Starting MongoDB Atlas Reaper Script...")

        # Validate credentials first
        validate_atlas_credentials()

        public_key = get_env_variable("ATLAS_PUBLIC_KEY")
        private_key = get_env_variable("ATLAS_PRIVATE_KEY")
        org_id = get_env_variable("ATLAS_ORG_ID")

        # Warn user about destructive operations
        print("⚠️  WARNING: This script will perform DESTRUCTIVE operations!")
        print(f"Organization ID: {org_id}")
        print(f"Projects older than {USER_DELETION_THRESHOLD} days will have:")
        print("  - All database users deleted")
        print("  - All Atlas users removed from projects")
        print(f"Projects older than {CLUSTER_DELETION_THRESHOLD} days will also have:")
        print("  - All clusters deleted")
        print("Additionally:")
        print(
            "  - ALL pending organization invitations will be deleted (if any old projects are found)"
        )

        confirm = input(
            f"\nType 'REAP PROJECTS OLDER THAN {USER_DELETION_THRESHOLD} DAYS' to confirm: "
        )

        if confirm != f"REAP PROJECTS OLDER THAN {USER_DELETION_THRESHOLD} DAYS":
            logger.info("Operation cancelled by user")
            print("Operation cancelled.")
            return 0

        auth = HTTPDigestAuth(public_key, private_key)

        projects = get_atlas_projects(org_id, auth)
        if not projects:
            logger.warning("No projects found or failed to retrieve projects")
            return 1

        # Fetch all organization invitations once to avoid repeated API calls
        logger.info("Fetching all organization invitations...")
        org_invitations = get_atlas_org_invitations(org_id, auth)
        logger.info(
            f"Found {len(org_invitations)} total invitations at organization level"
        )

        user_deletion_threshold_utc = CURRENT_DATE_UTC - timedelta(
            days=USER_DELETION_THRESHOLD
        )
        cluster_deletion_threshold_utc = CURRENT_DATE_UTC - timedelta(
            days=CLUSTER_DELETION_THRESHOLD
        )
        logger.info(
            f"User deletion threshold: {user_deletion_threshold_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        logger.info(
            f"Cluster deletion threshold: {cluster_deletion_threshold_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        total_processed = 0
        total_cleaned = 0
        total_errors = 0
        old_project_ids = set()  # Track IDs of projects older than 90 days

        for project in projects:
            project_id = project.get("id")
            project_name = project.get("name", "Unknown")
            created_str = project.get("created")

            if not all([project_id, project_name, created_str]):
                logger.warning(f"Skipping project with missing data: {project}")
                total_errors += 1
                continue

            try:
                # Ensure created_date is offset-aware (UTC) for proper comparison
                created_date = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            except ValueError:
                logger.error(
                    f"Could not parse creation date ('{created_str}') for project {project_name} ({project_id}). Skipping."
                )
                total_errors += 1
                continue

            total_processed += 1
            logger.info(
                f"\nProcessing Project: {project_name} (ID: {project_id}), Created: {created_date.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )

            if created_date < user_deletion_threshold_utc:
                logger.info(
                    f"Project {project_name} ({project_id}) is older than {USER_DELETION_THRESHOLD} days. Proceeding with user cleanup."
                )
                total_cleaned += 1
                old_project_ids.add(project_id)  # Track this old project

                # 1. Delete Database Users
                db_users = get_atlas_database_users(project_id, auth)
                if db_users:
                    logger.info(
                        f"  Found {len(db_users)} database users to process for project {project_name}"
                    )
                    for db_user in db_users:
                        username = db_user.get("username")
                        # Skip system users that shouldn't be deleted
                        if username in ["__onprem_monitoring", "admin"]:
                            logger.info(f"  Skipping system database user: {username}")
                            continue
                        if username:
                            delete_atlas_database_user(
                                project_id,
                                username,
                                auth,
                                db_user.get("databaseName", "admin"),
                            )
                else:
                    logger.info(f"  No database users found for project {project_name}")

                # 2. Remove Atlas Users from Project
                atlas_users_in_project = get_atlas_project_users(project_id, auth)
                if atlas_users_in_project:
                    logger.info(
                        f"  Found {len(atlas_users_in_project)} Atlas users with access to project {project_name}"
                    )
                    for atlas_user_summary in atlas_users_in_project:
                        user_id = atlas_user_summary.get("id")
                        if user_id:
                            delete_atlas_project_user(project_id, user_id, auth)
                else:
                    logger.info(
                        f"  No Atlas users found with access to project {project_name}"
                    )

                # 3. Delete Clusters if project is older than 120 days
                if created_date < cluster_deletion_threshold_utc:
                    logger.info(
                        f"  Project {project_name} is older than {CLUSTER_DELETION_THRESHOLD} days. Proceeding with cluster deletion."
                    )
                    clusters = get_atlas_clusters(project_id, auth)
                    if clusters:
                        logger.info(
                            f"  Found {len(clusters)} clusters to delete in project {project_name}"
                        )
                        for cluster in clusters:
                            cluster_name = cluster.get("name")
                            if cluster_name:
                                delete_atlas_cluster(project_id, cluster_name, auth)
                    else:
                        logger.info(f"  No clusters found in project {project_name}")
                else:
                    logger.info(
                        f"  Project {project_name} is not older than {CLUSTER_DELETION_THRESHOLD} days. Skipping cluster deletion."
                    )

            else:
                logger.info(
                    f"Project {project_name} ({project_id}) is not older than {USER_DELETION_THRESHOLD} days. Skipping user cleanup."
                )

        # 3. Delete ALL Organization Invitations when old projects are found
        if old_project_ids:
            logger.info(
                f"\nCleaning up ALL organization invitations due to old projects found..."
            )
            successful_inv, failed_inv = delete_invitations_for_old_projects(
                org_id, org_invitations, old_project_ids, auth
            )
            logger.info(
                f"Organization invitations cleanup: {successful_inv} successful, {failed_inv} failed"
            )
        else:
            logger.info(
                "\nNo old projects found, skipping organization invitation cleanup"
            )

        logger.info(
            f"Reaper script completed. Projects processed: {total_processed}, Cleaned: {total_cleaned}, Errors: {total_errors}"
        )
        return 0 if total_errors == 0 else 1

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
