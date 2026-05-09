"""
Test Snapshot Restore For Project

For each cluster in a given Atlas project, verifies that backup snapshots are
enabled, then exercises snapshot restore by creating a duplicate target cluster
(named "backup-test-job-{cluster-name}") and running an automated restore of
the latest snapshot into it. Work is done in batched phases across all
clusters: create all targets, wait for all targets to become IDLE, start all
restore jobs, wait for all restore jobs to finish. Optionally cleans up the
duplicate clusters afterward.

Prerequisites:
    - Python 3.6+
    - Required packages: requests, python-dotenv
    - Valid Atlas API credentials in .env file

Environment Variables:
    ATLAS_PUBLIC_KEY: MongoDB Atlas API Public Key
    ATLAS_PRIVATE_KEY: MongoDB Atlas API Private Key
    ATLAS_API_BASE_URL: (Optional) Atlas API Base URL

Usage:
    python test_snapshot_restore_for_project.py --project-id <PROJECT_ID> [--cleanup]

Safety Warning:
    This script creates new clusters (which incur cost) and performs restore
    jobs. With --cleanup it will also delete the duplicate target clusters
    once the restore completes. It never modifies or deletes the source
    clusters.
"""

import argparse
import copy
import datetime
import logging
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

load_dotenv()

ATLAS_API_BASE_URL = os.getenv(
    "ATLAS_API_BASE_URL", "https://cloud.mongodb.com/api/atlas/v2"
)
PUBLIC_KEY = os.getenv("ATLAS_PUBLIC_KEY")
PRIVATE_KEY = os.getenv("ATLAS_PRIVATE_KEY")

BACKUP_CLUSTER_MARKER = "-backup-test-job-"
CLUSTER_NAME_MAX_LEN = 64
POLL_INTERVAL_SECONDS = 30
CLUSTER_READY_TIMEOUT_SECONDS = 60 * 60  # 1 hour
RESTORE_TIMEOUT_SECONDS = 60 * 60 * 4  # 4 hours

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/test_snapshot_restore.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("test_snapshot_restore")


def validate_atlas_credentials():
    missing_vars = []
    if not PUBLIC_KEY:
        missing_vars.append("ATLAS_PUBLIC_KEY")
    if not PRIVATE_KEY:
        missing_vars.append("ATLAS_PRIVATE_KEY")
    if missing_vars:
        raise ValueError(
            f"Missing required Atlas API credentials: {', '.join(missing_vars)}"
        )


def make_atlas_api_request(
    method: str, url: str, **kwargs
) -> Optional[requests.Response]:
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        body = ""
        if getattr(e, "response", None) is not None:
            try:
                body = f" | body: {e.response.text}"
            except Exception:
                pass
        logger.error(f"API request failed: {method} {url} - {str(e)}{body}")
        return None


def get_clusters(project_id: str, auth, headers: dict) -> Optional[list]:
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters"
    all_clusters = []
    params = {"itemsPerPage": 500, "pageNum": 1}
    while True:
        response = make_atlas_api_request(
            "GET", url, headers=headers, auth=auth, params=params
        )
        if not response:
            return None
        data = response.json()
        results = data.get("results", [])
        all_clusters.extend(results)
        if not any(link.get("rel") == "next" for link in data.get("links", [])):
            break
        params["pageNum"] += 1
    return all_clusters


def get_cluster(project_id: str, cluster_name: str, auth, headers: dict) -> Optional[dict]:
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
    response = make_atlas_api_request("GET", url, headers=headers, auth=auth)
    if not response:
        return None
    return response.json()


def get_latest_snapshot(
    project_id: str, cluster_name: str, auth, headers: dict
) -> Optional[dict]:
    url = (
        f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
        f"/backup/snapshots"
    )
    response = make_atlas_api_request(
        "GET", url, headers=headers, auth=auth, params={"itemsPerPage": 1, "pageNum": 1}
    )
    if not response:
        return None
    results = response.json().get("results", [])
    if not results:
        return None
    return results[0]


def build_target_cluster_name(source_name: str, timestamp: str) -> str:
    """Derive a target cluster name that fits within Atlas's 64-char limit.

    Atlas also rejects two clusters in a project that share the first 23
    characters, so the source name must lead to keep those 23 chars distinct
    across different sources. Format: {source_name}{marker}{timestamp}.
    If the full name exceeds 64 chars, the source name is truncated (but the
    leading portion is preserved so the 23-char uniqueness holds).
    """
    suffix = f"{BACKUP_CLUSTER_MARKER}{timestamp}"
    available = CLUSTER_NAME_MAX_LEN - len(suffix)
    trimmed = source_name[:available].rstrip("-") if available > 0 else ""
    return f"{trimmed}{suffix}"


def is_backup_test_cluster(name: Optional[str]) -> bool:
    if not name:
        return False
    # Match both the current embedded-marker format and the legacy
    # "backup-test-job-<name>" prefix format from earlier runs.
    return BACKUP_CLUSTER_MARKER in name or name.startswith("backup-test-job-")


def build_target_cluster_body(source: dict, target_name: str) -> dict:
    """Strip server-managed fields from a cluster response and rename it."""
    body = copy.deepcopy(source)
    for field in (
        "id",
        "groupId",
        "createDate",
        "stateName",
        "mongoDBVersion",
        "mongoDBMajorVersion",
        "mongoDBEmployeeAccessGrant",
        "connectionStrings",
        "paused",
        "links",
        "replicaSetScalingStrategy",
        "featureCompatibilityVersion",
        "versionReleaseSystem",
    ):
        body.pop(field, None)

    for spec in body.get("replicationSpecs", []) or []:
        spec.pop("id", None)

    body["name"] = target_name
    return body


def create_cluster(
    project_id: str, cluster_body: dict, auth, headers: dict
) -> Optional[dict]:
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters"
    response = make_atlas_api_request(
        "POST", url, headers=headers, auth=auth, json=cluster_body
    )
    if not response:
        return None
    return response.json()


def start_restore_job(
    project_id: str,
    source_cluster_name: str,
    snapshot_id: str,
    target_cluster_name: str,
    auth,
    headers: dict,
) -> Optional[dict]:
    url = (
        f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{source_cluster_name}"
        f"/backup/restoreJobs"
    )
    body = {
        "deliveryType": "automated",
        "snapshotId": snapshot_id,
        "targetGroupId": project_id,
        "targetClusterName": target_cluster_name,
    }
    response = make_atlas_api_request(
        "POST", url, headers=headers, auth=auth, json=body
    )
    if not response:
        return None
    return response.json()


def get_restore_job(
    project_id: str, source_cluster_name: str, job_id: str, auth, headers: dict
) -> Optional[dict]:
    url = (
        f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{source_cluster_name}"
        f"/backup/restoreJobs/{job_id}"
    )
    response = make_atlas_api_request("GET", url, headers=headers, auth=auth)
    if not response:
        return None
    return response.json()


def restore_job_terminal(job: dict) -> bool:
    return bool(
        job.get("finishedAt")
        or job.get("failed")
        or job.get("cancelled")
        or job.get("expired")
    )


def restore_job_succeeded(job: dict) -> bool:
    return (
        bool(job.get("finishedAt"))
        and not job.get("failed")
        and not job.get("cancelled")
        and not job.get("expired")
    )


def delete_cluster(
    project_id: str, cluster_name: str, auth, headers: dict
) -> bool:
    url = f"{ATLAS_API_BASE_URL}/groups/{project_id}/clusters/{cluster_name}"
    response = make_atlas_api_request("DELETE", url, headers=headers, auth=auth)
    return response is not None and response.status_code in (202, 204)


def set_error(item: dict, message: str) -> None:
    logger.error(message)
    item["status"] = "error"
    item["message"] = message


def run(project_id: str, cleanup: bool) -> int:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/vnd.atlas.2025-02-19+json",
    }
    auth = HTTPDigestAuth(PUBLIC_KEY, PRIVATE_KEY)

    # --- Phase 1: fetch clusters ----------------------------------------
    logger.info(f"Fetching clusters in project {project_id}")
    clusters = get_clusters(project_id, auth, headers)
    if clusters is None:
        logger.error("Failed to fetch clusters")
        return 1
    if not clusters:
        logger.info("No clusters found in project; nothing to do")
        return 0

    source_clusters = [
        c for c in clusters if not is_backup_test_cluster(c.get("name"))
    ]
    logger.info(
        f"Found {len(source_clusters)} source clusters "
        f"(ignored {len(clusters) - len(source_clusters)} backup-test clusters)"
    )

    # items tracks per-cluster state across all phases.
    items = []
    for cluster in source_clusters:
        items.append({
            "source_name": cluster.get("name"),
            "source_cluster": cluster,
            "target_name": None,
            "target_created": False,
            "snapshot_id": None,
            "restore_job_id": None,
            "status": "pending",
            "message": "",
        })

    # --- Phase 2: check backups + latest snapshot -----------------------
    run_timestamp = datetime.datetime.utcnow().strftime("%y%m%d%H%M")
    logger.info(
        f"Phase: verifying backup enablement and latest snapshots "
        f"(target suffix: -{run_timestamp})"
    )
    for item in items:
        name = item["source_name"]
        if not item["source_cluster"].get("backupEnabled", False):
            msg = f"Snapshots are NOT enabled for cluster '{name}'"
            logger.warning(msg)
            item["status"] = "warning_no_backups"
            item["message"] = msg
            continue

        snapshot = get_latest_snapshot(project_id, name, auth, headers)
        if not snapshot:
            msg = f"Cluster '{name}' has backups enabled but no snapshots available"
            logger.warning(msg)
            item["status"] = "warning_no_snapshots"
            item["message"] = msg
            continue

        item["snapshot_id"] = snapshot.get("id")
        item["target_name"] = build_target_cluster_name(name, run_timestamp)
        logger.info(
            f"Cluster '{name}': snapshot {item['snapshot_id']} -> {item['target_name']}"
        )

    # --- Phase 3: create all target clusters ----------------------------
    to_create = [i for i in items if i["status"] == "pending"]
    logger.info(f"Phase: creating {len(to_create)} target clusters")
    for item in to_create:
        body = build_target_cluster_body(item["source_cluster"], item["target_name"])
        if not create_cluster(project_id, body, auth, headers):
            set_error(item, f"Failed to create target cluster '{item['target_name']}'")
            continue
        item["target_created"] = True
        item["status"] = "creating"
        logger.info(f"  create initiated for '{item['target_name']}'")

    # --- Phase 4: wait for all target clusters to become IDLE -----------
    waiting = [i for i in items if i["status"] == "creating"]
    logger.info(f"Phase: waiting for {len(waiting)} target clusters to become IDLE")
    deadline = time.time() + CLUSTER_READY_TIMEOUT_SECONDS
    while waiting and time.time() < deadline:
        still_waiting = []
        for item in waiting:
            cluster = get_cluster(project_id, item["target_name"], auth, headers)
            if cluster is None:
                set_error(
                    item,
                    f"Failed to fetch state for target cluster '{item['target_name']}'",
                )
                continue
            state = cluster.get("stateName")
            logger.info(f"  {item['target_name']}: {state}")
            if state == "IDLE":
                item["status"] = "ready_for_restore"
            else:
                still_waiting.append(item)
        waiting = still_waiting
        if waiting:
            time.sleep(POLL_INTERVAL_SECONDS)

    for item in waiting:
        set_error(
            item,
            f"Target cluster '{item['target_name']}' did not reach IDLE before timeout",
        )

    # --- Phase 5: start all restore jobs --------------------------------
    to_restore = [i for i in items if i["status"] == "ready_for_restore"]
    logger.info(f"Phase: starting {len(to_restore)} restore jobs")
    for item in to_restore:
        job = start_restore_job(
            project_id,
            item["source_name"],
            item["snapshot_id"],
            item["target_name"],
            auth,
            headers,
        )
        if not job:
            set_error(
                item,
                f"Failed to start restore for '{item['source_name']}' -> '{item['target_name']}'",
            )
            continue
        item["restore_job_id"] = job.get("id")
        item["status"] = "restoring"
        logger.info(
            f"  restore job {item['restore_job_id']} started "
            f"for '{item['source_name']}' -> '{item['target_name']}'"
        )

    # --- Phase 6: poll all restore jobs to completion -------------------
    restoring = [i for i in items if i["status"] == "restoring"]
    logger.info(f"Phase: polling {len(restoring)} restore jobs")
    deadline = time.time() + RESTORE_TIMEOUT_SECONDS
    while restoring and time.time() < deadline:
        still_restoring = []
        for item in restoring:
            job = get_restore_job(
                project_id, item["source_name"], item["restore_job_id"], auth, headers
            )
            if job is None:
                set_error(
                    item,
                    f"Failed to poll restore job {item['restore_job_id']} for '{item['source_name']}'",
                )
                continue
            if not restore_job_terminal(job):
                logger.info(f"  job {item['restore_job_id']} in progress")
                still_restoring.append(item)
                continue
            if restore_job_succeeded(job):
                item["status"] = "success"
                item["message"] = (
                    f"Restore succeeded for '{item['source_name']}' -> "
                    f"'{item['target_name']}' (job {item['restore_job_id']})"
                )
                logger.info(item["message"])
            else:
                set_error(
                    item,
                    f"Restore FAILED for '{item['source_name']}' -> "
                    f"'{item['target_name']}' (job {item['restore_job_id']}): "
                    f"cancelled={job.get('cancelled')} "
                    f"expired={job.get('expired')} "
                    f"failed={job.get('failed')}",
                )
        restoring = still_restoring
        if restoring:
            time.sleep(POLL_INTERVAL_SECONDS)

    for item in restoring:
        set_error(
            item,
            f"Restore job {item['restore_job_id']} did not finish before timeout",
        )

    # --- Summary --------------------------------------------------------
    successes = [i for i in items if i["status"] == "success"]
    warnings = [i for i in items if i["status"].startswith("warning")]
    errors = [i for i in items if i["status"] == "error"]

    logger.info("=" * 60)
    logger.info(
        f"Summary: {len(successes)} success, {len(warnings)} warnings, {len(errors)} errors"
    )
    for item in items:
        logger.info(f"  [{item['status']}] {item['source_name']}: {item['message']}")

    # --- Phase 7: cleanup ----------------------------------------------
    targets_created = [i["target_name"] for i in items if i["target_created"]]
    if cleanup and targets_created:
        logger.info(f"Phase: cleanup, deleting {len(targets_created)} target clusters")
        for target in targets_created:
            if delete_cluster(project_id, target, auth, headers):
                logger.info(f"  deletion initiated for '{target}'")
            else:
                logger.error(f"  failed to delete '{target}'")
    elif targets_created:
        logger.info(
            "Skipping cleanup (--cleanup not set). These target clusters still exist:"
        )
        for target in targets_created:
            logger.info(f"  - {target}")

    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(
        description="Test snapshot restore for every cluster in an Atlas project."
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="Atlas project (group) ID to operate on.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the created *-backup-test-job-* clusters after restore completes.",
    )
    args = parser.parse_args()

    try:
        validate_atlas_credentials()
        return run(args.project_id, args.cleanup)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
