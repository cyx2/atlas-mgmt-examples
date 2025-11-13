"""
Delete Empty Projects In Organization

This script identifies and removes empty MongoDB Atlas projects (projects with no clusters)
to optimize resource usage and maintain a clean organization structure.

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
    python delete_empty_projects_in_organization.py [--dry-run] [--auto-confirm]

Options:
    --dry-run: Show what would be deleted without performing actions
    --auto-confirm: Skip confirmation prompts (use with caution)

Safety Warning:
    This script performs DESTRUCTIVE operations on Atlas projects.
    Always use --dry-run first to review what will be deleted.
"""

import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/atlas_empty_projects_cleaner.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("atlas_empty_projects_cleaner")

# Load environment variables
load_dotenv()

# --- Configuration Constants ---
ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)


class AtlasAPI:
    """Handles all interactions with MongoDB Atlas API v2"""

    def __init__(self):
        self.base_url = ATLAS_API_BASE_URL
        self.public_key = os.getenv("ATLAS_PUBLIC_KEY")
        self.private_key = os.getenv("ATLAS_PRIVATE_KEY")
        self.org_id = os.getenv("ATLAS_ORG_ID")

        if not all([self.public_key, self.private_key, self.org_id]):
            raise ValueError("Missing required Atlas API credentials in .env file")

        # Verify credentials by making a test request
        self._verify_credentials()

    def _verify_credentials(self):
        """Verify API credentials and org_id by fetching organizations"""
        endpoint = "/orgs"
        orgs, success = self._make_request("get", endpoint, retry=1)

        if not success:
            logger.error(
                "Failed to verify API credentials. Check your public/private keys."
            )
            raise ValueError(
                "Failed to authenticate with Atlas API. Check your credentials."
            )

        # Verify that org_id exists in the list of accessible orgs
        org_ids = [org.get("id") for org in orgs.get("results", [])]
        if self.org_id not in org_ids:
            logger.error(
                f"Organization ID {self.org_id} not found in accessible organizations: {org_ids}"
            )
            raise ValueError(
                f"Organization ID {self.org_id} not found. Available orgs: {org_ids}"
            )

        logger.info(
            f"Successfully authenticated with Atlas API. Organization ID {self.org_id} is valid."
        )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        retry: int = 1,
        params: Optional[Dict] = None,
    ) -> Tuple[Dict, bool]:
        """
        Makes a request to the Atlas API with retry mechanism
        Returns a tuple of (response_data, success_flag)
        """
        url = f"{self.base_url}{endpoint}"
        headers = {"Accept": "application/vnd.atlas.2025-02-19+json"}
        auth = HTTPDigestAuth(self.public_key, self.private_key)

        for attempt in range(retry + 1):
            try:
                if method.lower() == "get":
                    response = requests.get(
                        url, auth=auth, headers=headers, params=params
                    )
                elif method.lower() == "post":
                    response = requests.post(
                        url, auth=auth, headers=headers, json=data, params=params
                    )
                elif method.lower() == "delete":
                    response = requests.delete(
                        url, auth=auth, headers=headers, params=params
                    )

                # Log the full response for debugging
                if response.status_code != 200:
                    logger.warning(
                        f"API response: {response.status_code} - {response.text}"
                    )

                response.raise_for_status()
                return response.json(), True

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"API request failed (attempt {attempt+1}/{retry+1}): {str(e)}"
                )
                if hasattr(e, "response") and e.response is not None:
                    logger.warning(f"Response content: {e.response.text}")

                if attempt < retry:
                    time.sleep(2)  # Wait before retrying
                else:
                    return {"error": str(e)}, False

    def get_projects_in_org(self) -> List[Dict]:
        """Get all projects in the organization with pagination support"""
        all_projects = []
        endpoint = f"/groups"
        base_params = {"orgId": self.org_id, "itemsPerPage": 500}  # Max items per page
        current_page = 1
        max_pages = 100  # Safety limit

        while True:
            params = {**base_params, "pageNum": current_page}
            result, success = self._make_request(
                "get", endpoint, retry=2, params=params
            )

            if not success:
                logger.error(f"API request failed for {endpoint} (page {current_page})")
                break

            projects = result.get("results", [])

            if not projects:
                break

            all_projects.extend(projects)
            logger.info(f"Retrieved {len(projects)} projects from page {current_page}")

            # Check if there are more pages (Atlas uses a "links" array with "next" relation)
            if not any(link.get("rel") == "next" for link in result.get("links", [])):
                break

            current_page += 1
            if current_page > max_pages:  # Safety break
                logger.warning(
                    f"Reached max_pages ({max_pages}) limit for {endpoint}. "
                    f"Not all projects might be fetched."
                )
                break

        logger.info(f"Total projects retrieved: {len(all_projects)}")
        return all_projects

    def get_clusters_in_project(self, project_id: str) -> List[Dict]:
        """Get all clusters in a project"""
        endpoint = f"/groups/{project_id}/clusters"
        result, success = self._make_request("get", endpoint, retry=2)

        if success:
            return result.get("results", [])
        return []

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project
        Returns success flag
        """
        endpoint = f"/groups/{project_id}"
        _, success = self._make_request("delete", endpoint, retry=2)
        return success


class AtlasEmptyProjectsCleaner:
    """
    Main class that identifies and deletes empty projects
    """

    def __init__(self):
        self.api = AtlasAPI()
        self.deleted_projects = []
        self.skipped_projects = []

    def delete_empty_projects(self, dry_run: bool = False):
        """
        Find and delete all projects with 0 clusters

        Parameters:
        dry_run (bool): If True, only report projects to be deleted without actually deleting them
        """
        # Get all projects in the organization
        projects = self.api.get_projects_in_org()

        if not projects:
            logger.info("No projects found in organization")
            return

        logger.info(f"Found {len(projects)} projects in organization")

        # Track projects and their status
        for project in projects:
            project_id = project.get("id")
            project_name = project.get("name")

            if not project_id:
                logger.warning(f"Project without ID found: {project}")
                continue

            # Get clusters in this project
            clusters = self.api.get_clusters_in_project(project_id)
            cluster_count = len(clusters)

            logger.info(
                f"Project '{project_name}' (ID: {project_id}) has {cluster_count} clusters"
            )

            if cluster_count == 0:
                # This is an empty project that should be deleted
                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would delete empty project '{project_name}' (ID: {project_id})"
                    )
                    self.deleted_projects.append(
                        {
                            "id": project_id,
                            "name": project_name,
                            "deleted": False,
                            "reason": "dry_run",
                        }
                    )
                else:
                    logger.info(
                        f"Deleting empty project '{project_name}' (ID: {project_id})"
                    )
                    if self.api.delete_project(project_id):
                        logger.info(
                            f"Successfully deleted project '{project_name}' (ID: {project_id})"
                        )
                        self.deleted_projects.append(
                            {
                                "id": project_id,
                                "name": project_name,
                                "deleted": True,
                                "reason": "success",
                            }
                        )
                    else:
                        logger.error(
                            f"Failed to delete project '{project_name}' (ID: {project_id})"
                        )
                        self.deleted_projects.append(
                            {
                                "id": project_id,
                                "name": project_name,
                                "deleted": False,
                                "reason": "api_error",
                            }
                        )
            else:
                # Project has clusters, should be skipped
                logger.info(
                    f"Skipping project '{project_name}' (ID: {project_id}) as it has {cluster_count} clusters"
                )
                self.skipped_projects.append(
                    {
                        "id": project_id,
                        "name": project_name,
                        "cluster_count": cluster_count,
                    }
                )

    def generate_report(self):
        """Generate a summary report of the operation"""
        successful_deletions = sum(1 for p in self.deleted_projects if p.get("deleted"))

        report = {
            "summary": {
                "total_projects_scanned": len(self.deleted_projects)
                + len(self.skipped_projects),
                "empty_projects_found": len(self.deleted_projects),
                "projects_with_clusters": len(self.skipped_projects),
                "successful_deletions": successful_deletions,
                "failed_deletions": len(self.deleted_projects) - successful_deletions,
            },
            "deleted_projects": self.deleted_projects,
            "skipped_projects": self.skipped_projects,
        }

        # Save report to file
        with open("logs/atlas_empty_projects_report.json", "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Report saved to logs/atlas_empty_projects_report.json")

        return report


def validate_credentials():
    """Validate that all required environment variables are present."""
    required_vars = ["ATLAS_PUBLIC_KEY", "ATLAS_PRIVATE_KEY", "ATLAS_ORG_ID"]
    missing_vars = []

    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )


def main():
    """Main function with comprehensive error handling and user confirmation."""
    try:
        logger.info("Starting MongoDB Atlas Empty Projects Cleaner...")

        # Validate credentials first
        validate_credentials()

        import argparse

        parser = argparse.ArgumentParser(
            description="MongoDB Atlas Empty Projects Cleaner"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Perform a dry run without actually deleting projects",
        )

        args = parser.parse_args()

        # Initialize cleaner
        cleaner = AtlasEmptyProjectsCleaner()

        if args.dry_run:
            logger.info("Running in DRY RUN mode - no projects will be deleted")
            print("🔍 DRY RUN MODE: No projects will actually be deleted")
        else:
            # Warn user about destructive operations
            print("⚠️  WARNING: This script will DELETE empty Atlas projects!")
            print(f"Organization ID: {os.getenv('ATLAS_ORG_ID')}")
            print("Projects without clusters will be permanently removed.")

            confirm = input("\nType 'DELETE EMPTY PROJECTS' to confirm: ")

            if confirm != "DELETE EMPTY PROJECTS":
                logger.info("Operation cancelled by user")
                print("Operation cancelled.")
                return 0

        # Run the cleaner
        cleaner.delete_empty_projects(dry_run=args.dry_run)

        # Generate and display report
        report = cleaner.generate_report()

        print("\nOperation Summary:")
        print(f"Total projects scanned: {report['summary']['total_projects_scanned']}")
        print(f"Empty projects found: {report['summary']['empty_projects_found']}")
        print(f"Projects with clusters: {report['summary']['projects_with_clusters']}")

        if args.dry_run:
            print(
                f"Projects that would be deleted: {report['summary']['empty_projects_found']}"
            )
        else:
            print(f"Successfully deleted: {report['summary']['successful_deletions']}")
            print(f"Failed deletions: {report['summary']['failed_deletions']}")

        print("\nDetailed report saved to logs/atlas_empty_projects_report.json")

        logger.info("Empty projects cleaner completed successfully")
        return 0

    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        print("\nOperation interrupted.")
        return 1
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        print(f"Configuration error: {str(e)}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
