"""
Provision Projects For Users

This script automates the creation and management of MongoDB Atlas projects and clusters
for multiple users. It handles user invitation, project creation, cluster provisioning,
and cleanup operations.

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
    python provision_projects_for_users.py --action <action> [--emails email1 email2 ...]

Actions:
    - provision: Create projects and clusters
    - delete-clusters: Delete clusters for specified emails
    - delete-projects: Delete projects for specified emails
    - delete-all-clusters: Delete all managed clusters
    - delete-all-projects: Delete all managed projects
"""

import json
import logging
import os
import time
from http import HTTPStatus
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/atlas_provisioner.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("atlas_provisioner")

# Load environment variables
load_dotenv()

# --- Configuration Constants ---
ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)

# Define the list of email addresses here
EMAILS_TO_PROVISION = [
    "example+ad90fb0a@mongodb.com",
    "example+ad90f10a@mongodb.com",
    "example+ad924520a@mongodb.com",
    "example+ad924134a@mongodb.com",
    "example+a134134a@mongodb.com",
]


class AtlasAPI:
    """Handles all interactions with MongoDB Atlas API v2"""

    def __init__(self):
        self.base_url = ATLAS_API_BASE_URL
        self.public_key = os.getenv("ATLAS_PUBLIC_KEY")
        self.private_key = os.getenv("ATLAS_PRIVATE_KEY")
        self.org_id = os.getenv("ATLAS_ORG_ID")

        # Track API request failures for reporting
        self.failed_requests = []
        self.total_requests = 0
        self.successful_requests = 0

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
        self, method: str, endpoint: str, data: Optional[Dict] = None, retry: int = 1
    ) -> Tuple[Dict, bool]:
        """
        Makes a request to the Atlas API with retry mechanism
        Returns a tuple of (response_data, success_flag)
        """
        url = f"{self.base_url}{endpoint}"
        headers = {"Accept": "application/vnd.atlas.2025-02-19+json"}
        auth = HTTPDigestAuth(self.public_key, self.private_key)

        # Track this request
        self.total_requests += 1

        for attempt in range(retry + 1):
            try:
                if method.lower() == "get":
                    response = requests.get(url, auth=auth, headers=headers)
                elif method.lower() == "post":
                    response = requests.post(url, auth=auth, headers=headers, json=data)
                elif method.lower() == "delete":
                    response = requests.delete(url, auth=auth, headers=headers)

                r = response.json()

                # Log the full response for debugging
                if not HTTPStatus(response.status_code).is_success:

                    if r["error"] == 409 and r["errorCode"] == "GROUP_ALREADY_EXISTS":
                        logger.info(f"Project {r["parameters"][0]} already exists.")
                        self.successful_requests += (
                            1  # Treat as success since project exists
                        )
                        return r, False
                    elif r["error"] == 409 and r["errorCode"] == "USER_ALREADY_EXISTS":
                        logger.info(f"User {r["parameters"][0]} already exists.")
                        self.successful_requests += (
                            1  # Treat as success since user exists
                        )
                        return r, False
                    else:
                        logger.warning(
                            f"API response: {response.status_code} - {response.text}"
                        )
                        # Record this failure
                        failure_info = {
                            "method": method.upper(),
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "error": r.get("error", "Unknown error"),
                            "error_code": r.get("errorCode", "Unknown error code"),
                            "attempt": attempt + 1,
                            "max_attempts": retry + 1,
                        }
                        self.failed_requests.append(failure_info)

                response.raise_for_status()
                self.successful_requests += 1
                return r, True

            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"API request failed (attempt {attempt+1}/{retry+1}): {str(e)}"
                )
                if hasattr(e, "response") and e.response is not None:
                    logger.warning(f"Response content: {e.response.text}")

                if attempt < retry:
                    time.sleep(2)  # Wait before retrying
                else:
                    # Record this failure after all retries exhausted
                    failure_info = {
                        "method": method.upper(),
                        "endpoint": endpoint,
                        "status_code": (
                            getattr(e.response, "status_code", "N/A")
                            if hasattr(e, "response") and e.response
                            else "N/A"
                        ),
                        "error": str(e),
                        "error_code": "REQUEST_EXCEPTION",
                        "attempt": attempt + 1,
                        "max_attempts": retry + 1,
                    }
                    self.failed_requests.append(failure_info)
                    return {"error": str(e)}, False

    def get_projects_in_org(self) -> List[Dict]:
        """Get all projects in the organization"""
        # API v2 uses this endpoint format for projects
        endpoint = f"/groups?orgId={self.org_id}"
        result, success = self._make_request("get", endpoint, retry=2)

        if success:
            return result.get("results", [])
        return []

    def create_project(self, name: str, owner_email: str) -> Tuple[Optional[str], bool]:
        """
        Create a new Atlas project in the organization
        Returns a tuple of (project_id, success_flag)
        """
        # API v2 endpoint for creating projects
        endpoint = f"/groups"
        data = {
            "name": name,
            "orgId": self.org_id,
            "tags": [{"key": "owner", "value": owner_email}],
        }

        result, success = self._make_request("post", endpoint, data, retry=2)

        if success:
            return result.get("id"), True
        return None, False

    def invite_user_to_project(
        self, project_id: str, email: str, role: str = "GROUP_OWNER"
    ) -> bool:
        """
        Invite a user to an Atlas project with specified role
        Available roles: GROUP_OWNER, GROUP_READ_ONLY, GROUP_DATA_ACCESS_ADMIN, GROUP_DATA_ACCESS_READ_WRITE, GROUP_DATA_ACCESS_READ_ONLY
        Returns success flag
        """
        endpoint = f"/groups/{project_id}/invites"

        data = {"roles": [role], "username": email}

        _, success = self._make_request("post", endpoint, data, retry=2)

        if success:
            logger.info(
                f"Successfully invited {email} to project {project_id} with role {role}"
            )
            return True
        else:
            logger.error(f"Failed to invite {email} to project {project_id}")
            return False

    def get_project_users(self, project_id: str) -> List[Dict]:
        """Get all users in a project"""
        endpoint = f"/groups/{project_id}/users"
        result, success = self._make_request("get", endpoint, retry=2)

        if success:
            return result.get("results", [])
        return []

    def get_clusters_in_project(self, project_id: str) -> List[Dict]:
        """Get all clusters in a project"""
        endpoint = f"/groups/{project_id}/clusters"
        result, success = self._make_request("get", endpoint, retry=2)

        if success:
            return result.get("results", [])
        return []

    def create_cluster(self, project_id: str, name: str, owner_email: str) -> bool:
        """
        Create an M0 cluster in a project
        Returns success flag
        """
        endpoint = f"/groups/{project_id}/clusters"

        data = {
            "clusterType": "REPLICASET",
            "name": name,
            "replicaSetScalingStrategy": "WORKLOAD_TYPE",
            "replicationSpecs": [
                {
                    "regionConfigs": [
                        {
                            "electableSpecs": {
                                "diskIOPS": 0,
                                "ebsVolumeType": "STANDARD",
                                "instanceSize": "M0",
                                "nodeCount": 1,
                            },
                            "priority": 7,
                            "providerName": "TENANT",
                            "backingProviderName": "AWS",
                            "regionName": "US_EAST_1",
                        }
                    ]
                }
            ],
            "tags": [{"key": "owner", "value": owner_email}],
        }

        _, success = self._make_request("post", endpoint, data, retry=2)
        return success

    def delete_cluster(self, project_id: str, cluster_name: str) -> bool:
        """
        Delete a cluster in a project
        Returns success flag
        """
        endpoint = f"/groups/{project_id}/clusters/{cluster_name}"
        _, success = self._make_request("delete", endpoint, retry=2)
        return success

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project
        Returns success flag
        """
        endpoint = f"/groups/{project_id}"
        _, success = self._make_request("delete", endpoint, retry=2)
        return success

    def get_request_summary(self) -> Dict:
        """Get summary of API request statistics"""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": len(self.failed_requests),
            "success_rate": (
                (self.successful_requests / self.total_requests * 100)
                if self.total_requests > 0
                else 0
            ),
        }

    def get_failure_details(self) -> List[Dict]:
        """Get detailed information about failed requests"""
        return self.failed_requests

    def has_failures(self) -> bool:
        """Check if there were any failed requests"""
        return len(self.failed_requests) > 0

    def reset_request_tracking(self):
        """Reset request tracking counters"""
        self.failed_requests = []
        self.total_requests = 0
        self.successful_requests = 0


class AtlasOwnershipTracker:
    """
    Manages the mapping between emails and their Atlas project IDs
    """

    def __init__(self, file_path: str = "logs/atlas_ownership.json"):
        self.file_path = file_path
        self.ownership_map = {}
        self._load_mapping()

    def _load_mapping(self):
        """Load existing mapping from file if it exists"""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r") as f:
                    self.ownership_map = json.load(f)
        except Exception as e:
            logger.error(f"Error loading ownership mapping: {str(e)}")
            self.ownership_map = {}

    def _save_mapping(self):
        """Save mapping to file"""
        try:
            with open(self.file_path, "w") as f:
                json.dump(self.ownership_map, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving ownership mapping: {str(e)}")

    def add_project(self, email: str, project_id: str, project_name: str):
        """Add a project mapping for an email"""
        self.ownership_map[email] = {
            "project_id": project_id,
            "project_name": project_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_mapping()

    def get_project_id(self, email: str) -> Optional[str]:
        """Get the project ID for an email if it exists"""
        if email in self.ownership_map:
            return self.ownership_map[email].get("project_id")
        return None

    def remove_project(self, email: str):
        """Remove a project mapping for an email"""
        if email in self.ownership_map:
            del self.ownership_map[email]
            self._save_mapping()
            return True
        return False

    def get_all_mappings(self) -> Dict:
        """Get all email to project mappings"""
        return self.ownership_map


class AtlasProvisioner:
    """
    Main class that provisions Atlas projects and clusters
    """

    def __init__(self):
        self.api = AtlasAPI()
        self.tracker = AtlasOwnershipTracker()

        # Track operation results
        self.operation_results = {
            "provision": {"success": 0, "failed": 0, "failed_emails": []},
            "delete_clusters": {"success": 0, "failed": 0, "failed_emails": []},
            "delete_projects": {"success": 0, "failed": 0, "failed_emails": []},
        }

    def provision_for_emails(self, emails: List[str]):
        """
        Main method to provision Atlas projects and clusters for a list of emails
        """
        # De-duplicate emails
        unique_emails = list(set(emails))
        logger.info(
            f"Processing {len(unique_emails)} unique emails out of {len(emails)} total"
        )

        # Get existing projects for comparison
        existing_projects = self.api.get_projects_in_org()
        existing_project_map = {p.get("name"): p.get("id") for p in existing_projects}

        for email in unique_emails:
            self._provision_for_email(email, existing_project_map)

    def _provision_for_email(self, email: str, existing_project_map: Dict):
        """
        Provision a project and cluster for a single email
        """
        try:
            # Check if email already has a project
            project_id = self.tracker.get_project_id(email)
            project_name = f"sandbox-{email}"

            if project_id:
                logger.info(f"Email {email} already has project {project_id}")

                # Verify the project still exists
                if project_id not in existing_project_map.values():
                    logger.warning(
                        f"Project {project_id} for {email} not found in Atlas, recreating"
                    )
                    project_id = None

            # Create a new project if needed
            if not project_id:
                logger.info(f"Creating new project for {email}")
                project_id, success = self.api.create_project(project_name, email)

                if not success or not project_id:
                    logger.error(f"Failed to create project for {email}")
                    self.operation_results["provision"]["failed"] += 1
                    self.operation_results["provision"]["failed_emails"].append(email)
                    return

                logger.info(f"Created project {project_id} for {email}")
                self.tracker.add_project(email, project_id, project_name)

                # Invite the user to the project with owner permissions
                if self.api.invite_user_to_project(project_id, email, "GROUP_OWNER"):
                    logger.info(
                        f"Invited {email} to project {project_id} with GROUP_OWNER role"
                    )
                else:
                    logger.warning(f"Failed to invite {email} to project {project_id}")
            else:
                # Check if user is already invited/added to the project
                project_users = self.api.get_project_users(project_id)
                user_emails = [user.get("username") for user in project_users]

                if email not in user_emails:
                    # Invite the user if not already in the project
                    if self.api.invite_user_to_project(
                        project_id, email, "GROUP_OWNER"
                    ):
                        logger.info(
                            f"Invited {email} to existing project {project_id} with GROUP_OWNER role"
                        )
                    else:
                        logger.warning(
                            f"Failed to invite {email} to existing project {project_id}"
                        )
                else:
                    logger.info(
                        f"User {email} is already a member of project {project_id}"
                    )

            # Check if the project has a cluster
            clusters = self.api.get_clusters_in_project(project_id)

            if not clusters:
                logger.info(f"No clusters found for project {project_id}, creating one")
                cluster_name = "sandbox-cluster"

                if self.api.create_cluster(project_id, cluster_name, email):
                    logger.info(
                        f"Created cluster {cluster_name} in project {project_id}"
                    )
                    self.operation_results["provision"]["success"] += 1
                else:
                    logger.error(
                        f"Failed to create cluster in project {project_id} for {email}"
                    )
                    self.operation_results["provision"]["failed"] += 1
                    self.operation_results["provision"]["failed_emails"].append(email)
            else:
                logger.info(
                    f"Project {project_id} already has {len(clusters)} clusters"
                )
                self.operation_results["provision"]["success"] += 1

        except Exception as e:
            logger.error(f"Exception during provisioning for {email}: {str(e)}")
            self.operation_results["provision"]["failed"] += 1
            self.operation_results["provision"]["failed_emails"].append(email)

    def delete_clusters_for_emails(self, emails: List[str]):
        """
        Delete only the clusters for a list of emails
        Returns a list of emails with deleted clusters
        """
        # De-duplicate emails
        unique_emails = list(set(emails))
        logger.info(
            f"Processing cluster deletion for {len(unique_emails)} unique emails"
        )

        emails_with_deleted_clusters = []

        for email in unique_emails:
            if self._delete_clusters_for_email(email):
                emails_with_deleted_clusters.append(email)

        return emails_with_deleted_clusters

    def _delete_clusters_for_email(self, email: str) -> bool:
        """
        Delete all clusters for a single email
        Returns True if any clusters were found and deletion was attempted
        """
        try:
            # Check if email has a project
            project_id = self.tracker.get_project_id(email)

            if not project_id:
                logger.info(f"No project found for {email}")
                return False

            # Get all clusters in the project
            clusters = self.api.get_clusters_in_project(project_id)

            if not clusters:
                logger.info(f"No clusters found for {email}'s project {project_id}")
                return False

            # Delete all clusters
            all_successful = True
            for cluster in clusters:
                cluster_name = cluster.get("name")
                logger.info(f"Deleting cluster {cluster_name} in project {project_id}")

                if self.api.delete_cluster(project_id, cluster_name):
                    logger.info(
                        f"Successfully initiated deletion for cluster {cluster_name}"
                    )
                else:
                    logger.error(f"Failed to delete cluster {cluster_name}")
                    all_successful = False

            if all_successful:
                self.operation_results["delete_clusters"]["success"] += 1
            else:
                self.operation_results["delete_clusters"]["failed"] += 1
                self.operation_results["delete_clusters"]["failed_emails"].append(email)

            return True

        except Exception as e:
            logger.error(f"Exception during cluster deletion for {email}: {str(e)}")
            self.operation_results["delete_clusters"]["failed"] += 1
            self.operation_results["delete_clusters"]["failed_emails"].append(email)
            return False

    def delete_projects_for_emails(self, emails: List[str]):
        """
        Delete the projects for a list of emails
        """
        # De-duplicate emails
        unique_emails = list(set(emails))
        logger.info(
            f"Processing project deletion for {len(unique_emails)} unique emails"
        )

        for email in unique_emails:
            self._delete_project_for_email(email)

    def _delete_project_for_email(self, email: str):
        """
        Delete the project for a single email
        """
        try:
            # Check if email has a project
            project_id = self.tracker.get_project_id(email)

            if not project_id:
                logger.info(f"No project found for {email}")
                return

            # Delete the project
            logger.info(f"Deleting project {project_id} for {email}")
            if self.api.delete_project(project_id):
                logger.info(f"Successfully deleted project {project_id}")
                # Remove from tracking
                self.tracker.remove_project(email)
                self.operation_results["delete_projects"]["success"] += 1
            else:
                logger.error(f"Failed to delete project {project_id}")
                self.operation_results["delete_projects"]["failed"] += 1
                self.operation_results["delete_projects"]["failed_emails"].append(email)

        except Exception as e:
            logger.error(f"Exception during project deletion for {email}: {str(e)}")
            self.operation_results["delete_projects"]["failed"] += 1
            self.operation_results["delete_projects"]["failed_emails"].append(email)

    def delete_all_clusters(self):
        """
        Delete all clusters that were provisioned by this script
        Returns a list of emails with deleted clusters
        """
        all_mappings = self.tracker.get_all_mappings()
        emails = list(all_mappings.keys())

        if not emails:
            logger.info("No provisioned resources found")
            return []

        logger.info(f"Deleting all clusters for {len(emails)} emails")
        return self.delete_clusters_for_emails(emails)

    def delete_all_projects(self):
        """
        Delete all projects that were provisioned by this script
        """
        all_mappings = self.tracker.get_all_mappings()
        emails = list(all_mappings.keys())

        if not emails:
            logger.info("No provisioned resources found")
            return

        logger.info(f"Deleting all projects for {len(emails)} emails")
        self.delete_projects_for_emails(emails)

    def get_operation_summary(self) -> Dict:
        """Get summary of all operations performed"""
        return {
            "provision_results": self.operation_results["provision"].copy(),
            "delete_cluster_results": self.operation_results["delete_clusters"].copy(),
            "delete_project_results": self.operation_results["delete_projects"].copy(),
            "api_summary": self.api.get_request_summary(),
            "has_failures": self.has_any_failures(),
        }

    def has_any_failures(self) -> bool:
        """Check if any operations had failures"""
        has_operation_failures = any(
            result["failed"] > 0 for result in self.operation_results.values()
        )
        return has_operation_failures or self.api.has_failures()

    def print_detailed_summary(self):
        """Print detailed summary of operations and failures"""
        summary = self.get_operation_summary()

        print("\n" + "=" * 60)
        print("OPERATION SUMMARY")
        print("=" * 60)

        # API Summary
        api_summary = summary["api_summary"]
        print(
            f"API Requests: {api_summary['total_requests']} total, "
            f"{api_summary['successful_requests']} successful, "
            f"{api_summary['failed_requests']} failed "
            f"({api_summary['success_rate']:.1f}% success rate)"
        )

        # Operation Results
        for operation, results in summary.items():
            if operation.endswith("_results"):
                op_name = operation.replace("_results", "").replace("_", " ").title()
                total = results["success"] + results["failed"]
                if total > 0:
                    print(
                        f"\n{op_name}: {total} total, {results['success']} successful, {results['failed']} failed"
                    )
                    if results["failed_emails"]:
                        print(f"  Failed emails: {', '.join(results['failed_emails'])}")

        # API Failure Details
        if self.api.has_failures():
            print(f"\nAPI FAILURE DETAILS:")
            print("-" * 40)
            for i, failure in enumerate(self.api.get_failure_details(), 1):
                print(f"{i}. {failure['method']} {failure['endpoint']}")
                print(f"   Status: {failure['status_code']}, Error: {failure['error']}")
                print(f"   Attempts: {failure['attempt']}/{failure['max_attempts']}")

        print("=" * 60)


def validate_credentials():
    """Validate that all required environment variables are present."""
    required_vars = [
        "ATLAS_PUBLIC_KEY",
        "ATLAS_PRIVATE_KEY",
        "ATLAS_ORG_ID",
        "ATLAS_API_BASE_URL",
    ]
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
        logger.info("Starting MongoDB Atlas Provisioner...")

        # Validate credentials first
        validate_credentials()

        import argparse

        parser = argparse.ArgumentParser(description="MongoDB Atlas Provisioner")
        parser.add_argument(
            "--action",
            choices=[
                "provision",
                "delete-clusters",
                "delete-projects",
                "delete-all-clusters",
                "delete-all-projects",
            ],
            default="provision",
            help="Action to perform: provision, delete-clusters, delete-projects, delete-all-clusters, or delete-all-projects",
        )
        parser.add_argument(
            "--emails",
            nargs="*",
            help="Emails to provision/delete (not needed for delete-all-* actions)",
        )

        args = parser.parse_args()

        # Initialize provisioner
        provisioner = AtlasProvisioner()

        # Get confirmation for destructive operations
        if args.action in [
            "delete-clusters",
            "delete-projects",
            "delete-all-clusters",
            "delete-all-projects",
        ]:
            print(f"⚠️  WARNING: This will perform DESTRUCTIVE operations!")
            print(f"Organization ID: {os.getenv('ATLAS_ORG_ID')}")
            print(f"Action: {args.action}")

            if args.action in ["delete-all-clusters", "delete-all-projects"]:
                confirm = input(f"\nType 'DELETE ALL' to confirm {args.action}: ")
                if confirm != "DELETE ALL":
                    logger.info("Operation cancelled by user")
                    print("Operation cancelled.")
                    return 0
            else:
                emails = args.emails or []
                print(
                    f"Target emails: {', '.join(emails) if emails else 'None specified'}"
                )
                confirm = input(f"\nType 'CONFIRM DELETE' to proceed: ")
                if confirm != "CONFIRM DELETE":
                    logger.info("Operation cancelled by user")
                    print("Operation cancelled.")
                    return 0

        if args.action == "provision":
            # Use provided emails or default to constant
            emails = args.emails if args.emails else EMAILS_TO_PROVISION

            if not emails:
                logger.error("No emails provided for provisioning")
                print(
                    "Error: No emails specified for provisioning. Use --emails or update EMAILS_TO_PROVISION constant."
                )
                return 1

            logger.info(f"Starting provisioning for {len(emails)} emails")
            provisioner.provision_for_emails(emails)

        elif args.action == "delete-clusters":
            # Must provide emails for selective deletion
            emails = args.emails

            if not emails:
                logger.error("No emails provided for cluster deletion")
                print(
                    "Error: No emails specified for cluster deletion. Use --emails parameter."
                )
                return 1

            logger.info(f"Starting cluster deletion for {len(emails)} emails")
            provisioner.delete_clusters_for_emails(emails)

        elif args.action == "delete-projects":
            # Must provide emails for selective deletion
            emails = args.emails

            if not emails:
                logger.error("No emails provided for project deletion")
                print(
                    "Error: No emails specified for project deletion. Use --emails parameter."
                )
                return 1

            logger.info(f"Starting project deletion for {len(emails)} emails")
            provisioner.delete_projects_for_emails(emails)

        elif args.action == "delete-all-clusters":
            logger.info("Deleting all provisioned clusters")
            provisioner.delete_all_clusters()

        elif args.action == "delete-all-projects":
            logger.info("Deleting all provisioned projects")
            provisioner.delete_all_projects()

        # Display detailed operation summary
        provisioner.print_detailed_summary()

        # Display ownership information
        print("\nAtlas Project Ownership:")
        mappings = provisioner.tracker.get_all_mappings()
        if mappings:
            for email, details in mappings.items():
                print(f"Email: {email}")
                print(f"  Project ID: {details.get('project_id')}")
                print(f"  Project Name: {details.get('project_name')}")
                print(f"  Created: {details.get('created_at')}")
                print("")
        else:
            print("No project mappings found.")

        # Determine final status based on failures
        if provisioner.has_any_failures():
            logger.warning("Atlas provisioner completed with failures")
            print("\nOperation completed with failures. See summary above for details.")
            return 1
        else:
            logger.info("Atlas provisioner completed successfully")
            print("\nOperation completed successfully!")
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
        logger.error(f"Unexpected error: {str(e)}")
        print(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
