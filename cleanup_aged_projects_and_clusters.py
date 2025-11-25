"""
Cleanup Aged Projects and Clusters

Automated cleanup of aged Atlas resources:
- Projects older than 90 days: Delete all group invitations, remove all database users and Atlas users
- Projects older than 120 days: Delete all clusters

Environment Variables:
    ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, ATLAS_ORG_ID
    ATLAS_API_BASE_URL (optional)

Usage: python cleanup_aged_projects_and_clusters.py
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Load environment variables and configure constants
load_dotenv()

ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)
CURRENT_DATE_UTC = datetime.now(timezone.utc)
USER_DELETION_THRESHOLD = 90
CLUSTER_DELETION_THRESHOLD = 120

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/reaper.log"), logging.StreamHandler()],
)
logger = logging.getLogger("atlas_reaper")


def validate_atlas_credentials() -> None:
    """Validate required Atlas environment variables."""
    required_vars = ["ATLAS_PUBLIC_KEY", "ATLAS_PRIVATE_KEY", "ATLAS_ORG_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

    logger.info("Atlas API credentials validated")


def get_env_variable(var_name: str) -> str:
    """Get environment variable with validation."""
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(f"Environment variable {var_name} not set")
    return value


def make_atlas_api_request(
    method: str, url: str, auth: HTTPDigestAuth, **kwargs
) -> Optional[requests.Response]:
    """Make Atlas API request with consistent error handling."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-03-12+json",
    }

    try:
        response = requests.request(
            method, url, auth=auth, headers=headers, timeout=30, **kwargs
        )
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {method} {url} - {str(e)}")
        return None


def get_all_paginated_items(
    url: str, auth: HTTPDigestAuth, item_key: str = "results"
) -> List[Dict[str, Any]]:
    """Retrieve all items from paginated Atlas API endpoint."""
    all_items = []
    page = 1

    while page <= 100:  # Safety limit
        response = make_atlas_api_request(
            "GET", url, auth, params={"pageNum": page, "itemsPerPage": 500}
        )
        if not response:
            break

        try:
            data = response.json()
        except ValueError:
            break

        if not data:
            break

        # Handle list response (non-paginated)
        if isinstance(data, list):
            all_items.extend(data)
            break

        # Handle dict response with results key (paginated)
        if item_key in data and data[item_key]:
            all_items.extend(data[item_key])
        else:
            break

        # Check for next page
        if not any(link.get("rel") == "next" for link in data.get("links", [])):
            break
        page += 1

    return all_items


def get_atlas_projects(org_id: str, auth: HTTPDigestAuth) -> List[Dict[str, Any]]:
    """Get all projects for organization."""
    url = f"{ATLAS_API_BASE_URL}/groups"
    projects = get_all_paginated_items(url, auth)
    logger.info(f"Found {len(projects)} projects")
    return projects


def get_atlas_database_users(
    project_id: str, auth: HTTPDigestAuth
) -> List[Dict[str, Any]]:
    """Get all database users for project."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/databaseUsers"
    return get_all_paginated_items(url, auth)


def get_atlas_project_users(
    project_id: str, auth: HTTPDigestAuth
) -> List[Dict[str, Any]]:
    """Get all Atlas users for project."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/users"
    return get_all_paginated_items(url, auth)


def get_atlas_clusters(project_id: str, auth: HTTPDigestAuth) -> List[Dict[str, Any]]:
    """Get all clusters for project."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters"
    return get_all_paginated_items(url, auth)


def get_atlas_group_invitations(
    project_id: str, auth: HTTPDigestAuth
) -> List[Dict[str, Any]]:
    """Get all group (project) invitations."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/invites"
    return get_all_paginated_items(url, auth)


def delete_atlas_resource(
    resource_type: str,
    project_id: str,
    resource_id: str,
    auth: HTTPDigestAuth,
    db_name: str = "admin",
) -> bool:
    """Generic function to delete Atlas resources."""
    endpoints = {
        "database_user": f"{ATLAS_API_BASE_URL}/groups/{project_id}/databaseUsers/{db_name}/{resource_id}",
        "project_user": f"{ATLAS_API_BASE_URL}/groups/{project_id}/users/{resource_id}",
        "cluster": f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{resource_id}",
    }

    url = endpoints.get(resource_type)
    if not url:
        logger.error(f"Unknown resource type: {resource_type}")
        return False

    response = make_atlas_api_request("DELETE", url, auth)
    success = response and response.status_code in [200, 202, 204]

    if success:
        logger.info(f"  Deleted {resource_type}: {resource_id}")
    else:
        logger.error(f"  Failed to delete {resource_type}: {resource_id}")

    return success


def delete_atlas_group_invitation(
    project_id: str, invitation_id: str, auth: HTTPDigestAuth
) -> bool:
    """Delete group (project) invitation."""
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/invites/{invitation_id}"
    response = make_atlas_api_request("DELETE", url, auth)

    if response and response.status_code in [200, 202, 204]:
        logger.info(f"  Deleted group invitation: {invitation_id}")
        return True

    logger.error(f"  Failed to delete group invitation: {invitation_id}")
    return False


def delete_all_group_invitations(
    project_id: str, project_name: str, auth: HTTPDigestAuth
) -> Tuple[int, int]:
    """Delete all group (project) invitations."""
    invitations = get_atlas_group_invitations(project_id, auth)

    if not invitations:
        return 0, 0

    logger.info(f"Found {len(invitations)} group invitations for {project_name}")

    successful = failed = 0
    for invitation in invitations:
        invitation_id = invitation.get("id")
        if invitation_id and delete_atlas_group_invitation(
            project_id, invitation_id, auth
        ):
            successful += 1
        else:
            failed += 1

    logger.info(
        f"Group invitation cleanup for {project_name}: {successful} successful, {failed} failed"
    )
    return successful, failed


def show_warning_and_confirm(org_id: str) -> bool:
    """Show warning and get user confirmation."""
    print("⚠️  WARNING: This script will perform DESTRUCTIVE operations!")
    print(f"Organization ID: {org_id}")
    print(f"Projects older than {USER_DELETION_THRESHOLD} days:")
    print("  - All group invitations deleted")
    print("  - All database users deleted")
    print("  - All Atlas users removed")
    print(f"Projects older than {CLUSTER_DELETION_THRESHOLD} days:")
    print("  - All clusters deleted")

    confirm = input(
        f"\nType 'REAP PROJECTS OLDER THAN {USER_DELETION_THRESHOLD} DAYS' to confirm: "
    )
    return confirm == f"REAP PROJECTS OLDER THAN {USER_DELETION_THRESHOLD} DAYS"


def cleanup_project_resources(
    project_id: str, project_name: str, auth: HTTPDigestAuth
) -> None:
    """Clean up all resources in a project."""
    # Delete all group invitations first
    delete_all_group_invitations(project_id, project_name, auth)

    # Delete database users
    db_users = get_atlas_database_users(project_id, auth)
    for user in db_users:
        username = user.get("username")
        if username and username not in ["__onprem_monitoring", "admin"]:
            delete_atlas_resource(
                "database_user",
                project_id,
                username,
                auth,
                user.get("databaseName", "admin"),
            )

    # Remove Atlas users
    atlas_users = get_atlas_project_users(project_id, auth)
    for user in atlas_users:
        user_id = user.get("id")
        if user_id:
            delete_atlas_resource("project_user", project_id, user_id, auth)


def cleanup_project_clusters(
    project_id: str, project_name: str, auth: HTTPDigestAuth
) -> None:
    """Delete all clusters in a project."""
    clusters = get_atlas_clusters(project_id, auth)
    for cluster in clusters:
        cluster_name = cluster.get("name")
        if cluster_name:
            delete_atlas_resource("cluster", project_id, cluster_name, auth)


def main():
    """Main function with error handling and user confirmation."""
    try:
        logger.info("Starting MongoDB Atlas Reaper Script")
        validate_atlas_credentials()

        org_id = get_env_variable("ATLAS_ORG_ID")
        if not show_warning_and_confirm(org_id):
            print("Operation cancelled.")
            return 0

        auth = HTTPDigestAuth(
            get_env_variable("ATLAS_PUBLIC_KEY"), get_env_variable("ATLAS_PRIVATE_KEY")
        )
        projects = get_atlas_projects(org_id, auth)

        if not projects:
            logger.warning("No projects found")
            return 1

        user_threshold = CURRENT_DATE_UTC - timedelta(days=USER_DELETION_THRESHOLD)
        cluster_threshold = CURRENT_DATE_UTC - timedelta(
            days=CLUSTER_DELETION_THRESHOLD
        )

        logger.info(f"User deletion threshold: {user_threshold.strftime('%Y-%m-%d')}")
        logger.info(
            f"Cluster deletion threshold: {cluster_threshold.strftime('%Y-%m-%d')}"
        )

        total_processed = total_cleaned = total_errors = 0

        for project in projects:
            project_id = project.get("id")
            project_name = project.get("name", "Unknown")
            created_str = project.get("created")

            if not all([project_id, project_name, created_str]):
                logger.warning(f"Skipping project with missing data: {project}")
                total_errors += 1
                continue

            try:
                created_date = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            except ValueError:
                logger.error(
                    f"Invalid date format for project {project_name}: {created_str}"
                )
                total_errors += 1
                continue

            total_processed += 1
            age_days = (CURRENT_DATE_UTC - created_date).days
            logger.info(f"Processing {project_name} (age: {age_days} days)")

            if created_date < user_threshold:
                logger.info(
                    f"Cleaning up project {project_name} (older than {USER_DELETION_THRESHOLD} days)"
                )
                total_cleaned += 1

                cleanup_project_resources(project_id, project_name, auth)

                if created_date < cluster_threshold:
                    logger.info(
                        f"Deleting clusters in {project_name} (older than {CLUSTER_DELETION_THRESHOLD} days)"
                    )
                    cleanup_project_clusters(project_id, project_name, auth)
            else:
                logger.info(f"Skipping {project_name} (not old enough)")

        logger.info(
            f"Completed: {total_processed} processed, {total_cleaned} cleaned, {total_errors} errors"
        )
        return 0 if total_errors == 0 else 1

    except KeyboardInterrupt:
        print("\nOperation interrupted.")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
