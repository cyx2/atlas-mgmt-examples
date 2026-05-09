"""
Test Snapshot Restore For Project

For each cluster in a given Atlas project, verifies that backup snapshots are
enabled, then exercises snapshot restore by creating a duplicate target cluster
(named "{source}-{timestamp}-backup-test-job") and running an automated
restore of the latest snapshot into it. Work is done in batched phases across
all clusters: create all targets, wait for all targets to become IDLE, start
all restore jobs, wait for all restore jobs to finish.

Warnings (not errors) are surfaced, with tier-specific context, for clusters
that cannot be tested:
    - M0 / M2 / M5 / FLEX / SERVERLESS: do not support Cloud Backup snapshots
    - backupEnabled=false on M10+: user has disabled backups
    - backupEnabled=true but no snapshots yet
    - latest snapshot's MongoDB version differs from the source cluster's
      major version (Atlas rejects such restores with INVALID_RESTORE_TO_TARGET)

Timeout recovery:
    If a target cluster doesn't reach IDLE, or a restore job doesn't finish,
    before the configured timeout, the stuck target is deleted and -- if
    retries remain -- the cluster is re-enqueued through create -> wait ->
    restore. Controlled by --max-retries (default 1).

Prerequisites:
    - Python 3.6+
    - Required packages: requests, python-dotenv
    - Valid Atlas API credentials in .env file

Environment Variables:
    ATLAS_PUBLIC_KEY: MongoDB Atlas API Public Key
    ATLAS_PRIVATE_KEY: MongoDB Atlas API Private Key
    ATLAS_API_BASE_URL: (Optional) Atlas API Base URL

Usage:
    python test_snapshot_restore_for_project.py --project-id <PROJECT_ID> \\
        [--cleanup] [--max-retries N]

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

BACKUP_CLUSTER_MARKER = "backup-test-job"
CLUSTER_NAME_MAX_LEN = 64
POLL_INTERVAL_SECONDS = 30
CLUSTER_READY_TIMEOUT_SECONDS = 60 * 60  # 1 hour
RESTORE_TIMEOUT_SECONDS = 60 * 60 * 4  # 4 hours
DEFAULT_MAX_RETRIES = 1  # retry count for IDLE / restore timeouts

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

    Atlas enforces two naming rules that shape this function:
      1. Cluster names must be <= 64 chars.
      2. No two clusters in a project may share the first 23 characters.

    To satisfy (2), the timestamp must appear inside the first 23 chars --
    otherwise repeat runs against the same source name collide (e.g., two
    runs of 'Cluster0-...-backup-test-job-...' both lead with the same 23).
    Format: {source_name}-{timestamp}-{marker}. If the full name exceeds 64
    chars, the source name is truncated (the leading timestamp+marker stay
    intact, preserving uniqueness).
    """
    suffix = f"-{timestamp}-{BACKUP_CLUSTER_MARKER}"
    available = CLUSTER_NAME_MAX_LEN - len(suffix)
    trimmed = source_name[:available].rstrip("-") if available > 0 else ""
    return f"{trimmed}{suffix}"


def is_backup_test_cluster(name: Optional[str]) -> bool:
    if not name:
        return False
    # Match the current format, and legacy formats from earlier runs
    # so repeat runs don't treat those artifacts as source clusters.
    return (
        BACKUP_CLUSTER_MARKER in name
        or name.startswith("backup-test-job-")
    )


def build_target_cluster_body(source: dict, target_name: str) -> dict:
    """Strip server-managed fields from a cluster response and rename it."""
    body = copy.deepcopy(source)
    # Strip read-only / server-managed fields. We intentionally keep:
    #   - mongoDBMajorVersion: target must match the snapshot's version or
    #     restore fails with INVALID_RESTORE_TO_TARGET.
    #   - versionReleaseSystem: required for minor versions like 8.1/8.2/8.3.
    #     Those versions live on the CONTINUOUS track; omitting this defaults
    #     to LTS, which rejects them with MONGODB_MAJOR_VERSION_INVALID.
    for field in (
        "id",
        "groupId",
        "createDate",
        "stateName",
        "mongoDBVersion",
        "mongoDBEmployeeAccessGrant",
        "connectionStrings",
        "paused",
        "links",
        "replicaSetScalingStrategy",
        "featureCompatibilityVersion",
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


def snapshot_major_version(snapshot: dict) -> Optional[str]:
    """Extract the major version (e.g. '7.0', '8.0') from a snapshot.

    Atlas snapshot responses include a `mongodVersion` like '8.3.0'. We keep
    the first two dotted segments so it can be compared against the cluster's
    `mongoDBMajorVersion`.
    """
    raw = snapshot.get("mongodVersion") or snapshot.get("mongoDBVersion")
    if not raw:
        return None
    parts = raw.split(".")
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[1]}"


def cluster_instance_size(cluster: dict) -> Optional[str]:
    """Extract the electable instance size (e.g. 'M0', 'M10', 'FLEX') from a
    cluster response. The field nests inside replicationSpecs[].regionConfigs[],
    and both electableSpecs and (for analytics-only) readOnlySpecs may carry
    a size; we return the first non-empty one."""
    for spec in cluster.get("replicationSpecs", []) or []:
        for region in spec.get("regionConfigs", []) or []:
            for key in ("electableSpecs", "readOnlySpecs", "analyticsSpecs"):
                size = (region.get(key) or {}).get("instanceSize")
                if size:
                    return size
    return None


def explain_no_backups(cluster: dict) -> str:
    """Return a short human-readable reason why a cluster has no cloud backups.

    Atlas Cloud Backup (the `/backup/snapshots` endpoint this script uses) is
    only available on M10+ dedicated tiers. M0 cannot enable it at all; Flex
    has its own separate always-on backup system; Serverless is deprecated.
    See: https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/
    """
    size = cluster_instance_size(cluster)
    if not size:
        return "could not determine cluster tier from API response"
    size_upper = size.upper()
    if size_upper == "M0":
        return "M0 free tier does not support Cloud Backup"
    if size_upper in ("M2", "M5"):
        return f"shared tier {size} does not support Cloud Backup (legacy, migrate to Flex or M10+)"
    if size_upper == "FLEX":
        return (
            "Flex clusters use a separate always-on backup system, not Cloud Backup; "
            "this script's snapshot/restore endpoints only apply to M10+ dedicated tiers"
        )
    if size_upper == "SERVERLESS":
        return "Serverless instances are deprecated and no longer support backups"
    return (
        f"tier {size} supports Cloud Backup but it is disabled on this cluster; "
        f"enable by setting backupEnabled=true"
    )


def set_error(item: dict, message: str) -> None:
    logger.error(message)
    item["status"] = "error"
    item["message"] = message


def create_targets(items: list, project_id: str, auth, headers: dict) -> None:
    """Phase 3: issue POST /clusters for each pending item."""
    to_create = [i for i in items if i["status"] == "pending_create"]
    logger.info(f"Phase: creating {len(to_create)} target clusters")
    for item in to_create:
        body = build_target_cluster_body(item["source_cluster"], item["target_name"])
        if not create_cluster(project_id, body, auth, headers):
            set_error(item, f"Failed to create target cluster '{item['target_name']}'")
            continue
        item["target_created"] = True
        item["status"] = "creating"
        logger.info(f"  create initiated for '{item['target_name']}'")


def wait_for_targets_idle(items: list, project_id: str, auth, headers: dict) -> list:
    """Phase 4: poll until each target is IDLE. Returns the list of items that
    timed out (still in 'creating' state). Does not mutate those items'
    statuses -- caller decides whether to retry or mark as error."""
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
    return waiting  # items that didn't reach IDLE


def start_restores(items: list, project_id: str, auth, headers: dict) -> None:
    """Phase 5: POST a restore job for each cluster that reached IDLE."""
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


def poll_restores(items: list, project_id: str, auth, headers: dict) -> list:
    """Phase 6: poll each restore job until terminal. Returns items that
    timed out (still 'restoring'); statuses for those are not mutated."""
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
    return restoring  # items whose restore didn't finish


def recover_timed_out(
    timed_out: list,
    reason: str,
    max_retries: int,
    project_id: str,
    auth,
    headers: dict,
) -> None:
    """Handle items that hit a timeout.

    For each timed-out item, delete the stuck target cluster (so it doesn't
    sit around costing money) and, if retries remain, reset its state so the
    caller can re-run the create -> wait -> restore pipeline on it. If no
    retries remain, mark the item as errored.
    """
    for item in timed_out:
        target = item["target_name"]
        logger.warning(
            f"{reason} for '{item['source_name']}' -> '{target}'; deleting stuck target"
        )
        if not delete_cluster(project_id, target, auth, headers):
            logger.error(f"  failed to delete stuck target '{target}'")
        item["target_created"] = False
        item["restore_job_id"] = None
        if item["retries_remaining"] > 0:
            item["retries_remaining"] -= 1
            item["status"] = "pending_create"
            logger.info(
                f"  retrying '{item['source_name']}' "
                f"({item['retries_remaining']} retries left after this one)"
            )
        else:
            set_error(
                item,
                f"{reason} for '{item['source_name']}' -> '{target}'; "
                f"out of retries (stuck target deleted)",
            )


def run(project_id: str, cleanup: bool, max_retries: int = DEFAULT_MAX_RETRIES) -> int:
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
            "retries_remaining": max_retries,
        })

    # --- Phase 2: check backups + latest snapshot -----------------------
    run_timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%y%m%d%H%M%S")
    logger.info(
        f"Phase: verifying backup enablement and latest snapshots "
        f"(target suffix: -{run_timestamp})"
    )
    for item in items:
        name = item["source_name"]
        if not item["source_cluster"].get("backupEnabled", False):
            reason = explain_no_backups(item["source_cluster"])
            msg = f"Snapshots are NOT enabled for cluster '{name}': {reason}"
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

        cluster_version = item["source_cluster"].get("mongoDBMajorVersion")
        snap_version = snapshot_major_version(snapshot)
        if cluster_version and snap_version and cluster_version != snap_version:
            msg = (
                f"Version mismatch for cluster '{name}': cluster is on "
                f"{cluster_version} but latest snapshot is on {snap_version}; "
                f"skipping (Atlas restore requires matching major versions)"
            )
            logger.warning(msg)
            item["status"] = "warning_version_mismatch"
            item["message"] = msg
            continue

        item["snapshot_id"] = snapshot.get("id")
        item["target_name"] = build_target_cluster_name(name, run_timestamp)
        item["status"] = "pending_create"
        logger.info(
            f"Cluster '{name}': snapshot {item['snapshot_id']} "
            f"(v{snap_version or 'unknown'}) -> {item['target_name']}"
        )

    # --- Phases 3-6: create, wait-IDLE, restore, poll -- with retry on timeout.
    # On timeout (IDLE or restore), delete the stuck target and, if retries
    # remain, push the item back through create -> wait. Otherwise mark as
    # error. We loop until no items are ready for another attempt.
    while any(i["status"] == "pending_create" for i in items):
        create_targets(items, project_id, auth, headers)
        idle_timeouts = wait_for_targets_idle(items, project_id, auth, headers)
        if idle_timeouts:
            recover_timed_out(
                idle_timeouts,
                "Target cluster did not reach IDLE before timeout",
                max_retries,
                project_id,
                auth,
                headers,
            )
            continue  # retry attempts re-enter at create_targets

        start_restores(items, project_id, auth, headers)
        restore_timeouts = poll_restores(items, project_id, auth, headers)
        if restore_timeouts:
            recover_timed_out(
                restore_timeouts,
                "Restore job did not finish before timeout",
                max_retries,
                project_id,
                auth,
                headers,
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
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=(
            "How many times to retry a cluster on IDLE/restore timeout. On each "
            "timeout the stuck target is deleted and the pipeline re-enters at "
            f"create. Default: {DEFAULT_MAX_RETRIES}."
        ),
    )
    args = parser.parse_args()

    try:
        validate_atlas_credentials()
        return run(args.project_id, args.cleanup, args.max_retries)
    except KeyboardInterrupt:
        logger.warning("Operation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
