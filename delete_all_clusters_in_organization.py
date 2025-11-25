"""
Delete All Clusters In Organization

This script provides functionality to delete all clusters within MongoDB Atlas projects
across an organization. Useful for cleanup operations and environment management.

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
    python delete_all_clusters_in_organization.py

Safety Warning:
    This script performs DESTRUCTIVE operations on all clusters.
    Use with extreme caution. Ensure you have backups of critical data.
"""

import logging
import os
from typing import Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Load environment variables
load_dotenv()

# --- Configuration Constants ---
ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)
PUBLIC_KEY: Optional[str] = os.getenv("ATLAS_PUBLIC_KEY")
PRIVATE_KEY: Optional[str] = os.getenv("ATLAS_PRIVATE_KEY")
ORGANIZATION_ID: Optional[str] = os.getenv("ATLAS_ORG_ID")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/delete_all_clusters.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("delete_all_clusters")


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

    logger.info("Atlas API credentials validated successfully")


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


def get_all_paginated_projects(org_id: str, auth, headers: dict) -> list:
    """
    Retrieve all projects from a paginated Atlas API endpoint.

    Args:
        org_id: The organization ID
        auth: HTTPDigestAuth object for authentication
        headers: Request headers

    Returns:
        List of all projects across all pages
    """
    all_projects = []
    projects_url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/groups"
    params = {"itemsPerPage": 500}  # Max items per page
    current_page = 1
    max_pages = 100  # Safety limit

    while True:
        params["pageNum"] = current_page
        response = make_atlas_api_request(
            "GET", projects_url, headers=headers, auth=auth, params=params
        )

        # Check if API request failed
        if not response:
            logger.error(f"API request failed for {projects_url} (page {current_page})")
            break

        data = response.json()
        projects = data.get("results", [])

        if not projects:
            break

        all_projects.extend(projects)
        logger.info(f"Retrieved {len(projects)} projects from page {current_page}")

        # Check if there are more pages (Atlas uses a "links" array with "next" relation)
        if not any(link.get("rel") == "next" for link in data.get("links", [])):
            break

        current_page += 1
        if current_page > max_pages:  # Safety break
            logger.warning(
                f"Reached max_pages ({max_pages}) limit for {projects_url}. "
                f"Not all projects might be fetched."
            )
            break

    logger.info(f"Total projects retrieved: {len(all_projects)}")
    return all_projects


def delete_all_clusters_in_org(org_id: str) -> bool:
    """
    Delete all clusters within Atlas projects in an organization.

    Args:
        org_id: The ID of the Atlas organization

    Returns:
        True if operation completed successfully, False otherwise
    """
    if not org_id:
        logger.error("Organization ID is required but not provided")
        return False

    logger.info(f"Starting cluster deletion for organization: {org_id}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    # Get all projects in the organization (with pagination support)
    projects = get_all_paginated_projects(org_id, auth, headers)

    if not projects:
        logger.error("Failed to fetch projects from organization or no projects found")
        return False

    logger.info(f"Found {len(projects)} projects in organization")

    total_clusters_deleted = 0
    total_failures = 0

    for project in projects:
        project_id = project.get("id")
        project_name = project.get("name", "Unknown")

        if not project_id:
            logger.warning(f"Skipping project with missing ID: {project_name}")
            continue

        logger.info(f"Processing project: {project_name} (ID: {project_id})")

        # Get all clusters in the project
        clusters_url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters"
        clusters_response = make_atlas_api_request(
            "GET", clusters_url, headers=headers, auth=auth
        )

        if not clusters_response:
            logger.error(f"Failed to fetch clusters for project {project_name}")
            total_failures += 1
            continue

        clusters = clusters_response.json().get("results", [])
        logger.info(f"Found {len(clusters)} clusters in project {project_name}")

        for cluster in clusters:
            cluster_name = cluster.get("name")

            if not cluster_name:
                logger.warning(
                    f"Skipping cluster with missing name in project {project_name}"
                )
                continue

            logger.info(f"Deleting cluster: {cluster_name} in project {project_name}")

            # Delete the cluster
            delete_url = (
                f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
            )
            delete_response = make_atlas_api_request(
                "DELETE", delete_url, headers=headers, auth=auth
            )

            if delete_response and delete_response.status_code == 202:
                logger.info(
                    f"Successfully initiated deletion for cluster: {cluster_name}"
                )
                total_clusters_deleted += 1
            else:
                logger.error(f"Failed to delete cluster: {cluster_name}")
                total_failures += 1

    logger.info(
        f"Operation completed. Clusters deleted: {total_clusters_deleted}, Failures: {total_failures}"
    )
    return total_failures == 0


def main():
    """Main function with comprehensive error handling."""
    try:
        # Validate credentials
        validate_atlas_credentials()

        logger.info("Starting MongoDB Atlas cluster deletion tool")

        # Confirm destructive operation
        print("⚠️  WARNING: This will delete ALL clusters in the organization!")
        print(f"Organization ID: {ORGANIZATION_ID}")
        confirm = input("Type 'DELETE ALL CLUSTERS' to confirm: ")

        if confirm != "DELETE ALL CLUSTERS":
            logger.info("Operation cancelled by user")
            print("Operation cancelled.")
            return 0

        success = delete_all_clusters_in_org(ORGANIZATION_ID)

        if success:
            logger.info("All operations completed successfully")
            return 0
        else:
            logger.error("Some operations failed")
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
