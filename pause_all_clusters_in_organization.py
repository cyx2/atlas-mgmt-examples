"""
Pause All Clusters In Organization

This script provides functionality to pause all clusters within MongoDB Atlas projects
across an organization. Useful for cost management and temporary environment shutdown.

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
    python pause_all_clusters_in_organization.py

Safety Warning:
    This script performs operations that will pause all clusters in the organization.
    Paused clusters will be inaccessible until resumed. Use with caution.
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
PUBLIC_KEY = os.getenv("ATLAS_PUBLIC_KEY")
PRIVATE_KEY = os.getenv("ATLAS_PRIVATE_KEY")
ORGANIZATION_ID = os.getenv("ATLAS_ORG_ID")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/pause_all_clusters.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("pause_all_clusters")


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


# Validate credentials after logger is configured
validate_atlas_credentials()


def make_atlas_api_request(
    method: str, url: str, **kwargs
) -> Optional[requests.Response]:
    """
    Make an Atlas API request with proper error handling.

    Args:
        method: HTTP method (GET, POST, PATCH, etc.)
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


def pause_all_clusters_in_org(org_id: str) -> bool:
    """
    Pause all clusters within Atlas projects in an organization.

    Args:
        org_id: The ID of the Atlas organization

    Returns:
        True if operation completed successfully, False otherwise
    """
    if not org_id:
        logger.error("Organization ID is required but not provided")
        return False

    logger.info(f"Starting cluster pause operation for organization: {org_id}")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    # Get all projects in the organization
    projects_url = f"{ATLAS_API_BASE_URL}/orgs/{org_id}/groups"
    response = make_atlas_api_request("GET", projects_url, headers=headers, auth=auth)

    if not response:
        logger.error("Failed to fetch projects from organization")
        return False

    projects = response.json().get("results", [])
    logger.info(f"Found {len(projects)} projects in organization")

    total_clusters_paused = 0
    total_failures = 0
    total_already_paused = 0

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
            current_paused_state = cluster.get("paused", False)

            if not cluster_name:
                logger.warning(
                    f"Skipping cluster with missing name in project {project_name}"
                )
                continue

            if current_paused_state:
                logger.info(f"Cluster {cluster_name} is already paused, skipping")
                total_already_paused += 1
                continue

            logger.info(f"Pausing cluster: {cluster_name} in project {project_name}")

            # Pause the cluster
            pause_url = (
                f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
            )
            pause_data = {"paused": True}
            pause_response = make_atlas_api_request(
                "PATCH", pause_url, headers=headers, auth=auth, json=pause_data
            )

            if pause_response and pause_response.status_code in [200, 202]:
                logger.info(f"Successfully initiated pause for cluster: {cluster_name}")
                total_clusters_paused += 1
            else:
                logger.error(f"Failed to pause cluster: {cluster_name}")
                total_failures += 1

    logger.info(
        f"Operation completed. Clusters paused: {total_clusters_paused}, "
        f"Already paused: {total_already_paused}, Failures: {total_failures}"
    )
    return total_failures == 0


def main():
    """Main function with comprehensive error handling."""
    try:
        logger.info("Starting MongoDB Atlas cluster pause tool")

        # Confirm operation
        print("⚠️  WARNING: This will pause ALL clusters in the organization!")
        print(f"Organization ID: {ORGANIZATION_ID}")
        print("Paused clusters will be inaccessible until resumed.")
        confirm = input("Type 'PAUSE ALL CLUSTERS' to confirm: ")

        if confirm != "PAUSE ALL CLUSTERS":
            logger.info("Operation cancelled by user")
            print("Operation cancelled.")
            return 0

        success = pause_all_clusters_in_org(ORGANIZATION_ID)

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
