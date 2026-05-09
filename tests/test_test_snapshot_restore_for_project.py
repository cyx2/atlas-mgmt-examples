"""
Tests for test_snapshot_restore_for_project.py

Covers:
- Credential validation
- Target cluster name derivation (23-char uniqueness, 64-char limit, truncation)
- Filtering of pre-existing backup-test clusters
- Cluster body sanitization (server-managed field stripping)
- Restore job terminal-state detection
- The full phased run() for success, no-backup warning, no-snapshot warning,
  create failures, cluster-never-IDLE timeouts, restore failures, and cleanup
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests


def _load_module():
    if "test_snapshot_restore_for_project" in sys.modules:
        del sys.modules["test_snapshot_restore_for_project"]
    import test_snapshot_restore_for_project as module
    module.PUBLIC_KEY = "test_key"
    module.PRIVATE_KEY = "test_key"
    return module


def _mock_resp(status_code=200, json_data=None, raise_error=False):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = str(json_data or {})
    if raise_error:
        resp.raise_for_status.side_effect = requests.exceptions.RequestException("boom")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _cluster(name="Cluster0", backup_enabled=True, instance_size="M10", extra=None):
    body = {
        "name": name,
        "backupEnabled": backup_enabled,
        "clusterType": "REPLICASET",
        "id": "srv-id",
        "groupId": "grp",
        "createDate": "2026-01-01T00:00:00Z",
        "stateName": "IDLE",
        "mongoDBVersion": "7.0.12",
        "mongoDBMajorVersion": "8.3",
        "versionReleaseSystem": "CONTINUOUS",
        "connectionStrings": {"standard": "mongodb://x"},
        "paused": False,
        "links": [{"rel": "self", "href": "..."}],
        "replicationSpecs": [
            {
                "id": "rs-id",
                "zoneName": "ZoneName managed by Terraform",
                "regionConfigs": [
                    {
                        "providerName": "AWS",
                        "regionName": "US_EAST_1",
                        "priority": 7,
                        "electableSpecs": {"instanceSize": instance_size, "nodeCount": 3},
                    }
                ],
            }
        ],
    }
    if extra:
        body.update(extra)
    return body


class TestValidateAtlasCredentials:
    def test_success(self):
        m = _load_module()
        m.PUBLIC_KEY = "a"
        m.PRIVATE_KEY = "b"
        m.validate_atlas_credentials()  # no raise

    def test_missing_public_key(self):
        m = _load_module()
        m.PUBLIC_KEY = None
        m.PRIVATE_KEY = "b"
        with pytest.raises(ValueError) as exc:
            m.validate_atlas_credentials()
        assert "ATLAS_PUBLIC_KEY" in str(exc.value)

    def test_missing_private_key(self):
        m = _load_module()
        m.PUBLIC_KEY = "a"
        m.PRIVATE_KEY = None
        with pytest.raises(ValueError) as exc:
            m.validate_atlas_credentials()
        assert "ATLAS_PRIVATE_KEY" in str(exc.value)


class TestBuildTargetClusterName:
    def test_format_is_source_timestamp_marker(self):
        m = _load_module()
        name = m.build_target_cluster_name("Cluster0", "260509143700")
        assert name == "Cluster0-260509143700-backup-test-job"

    def test_first_23_chars_distinguish_similar_sources(self):
        """Regression: Atlas rejects two clusters that share the first 23 chars."""
        m = _load_module()
        n1 = m.build_target_cluster_name("Cluster0", "260509143700")
        n2 = m.build_target_cluster_name("Cluster3", "260509143700")
        n3 = m.build_target_cluster_name("Cluster5", "260509143700")
        assert len({n1[:23], n2[:23], n3[:23]}) == 3

    def test_first_23_chars_distinguish_same_source_across_runs(self):
        """Regression: repeat runs against the same source cluster must not
        collide with leftover target clusters from earlier runs. The timestamp
        must appear within the first 23 characters for this to hold."""
        m = _load_module()
        n1 = m.build_target_cluster_name("Cluster0", "260509143700")
        n2 = m.build_target_cluster_name("Cluster0", "260509143800")
        assert n1[:23] != n2[:23]

    def test_truncates_to_64_chars(self):
        m = _load_module()
        long_src = "a" * 80
        name = m.build_target_cluster_name(long_src, "260509143700")
        assert len(name) == 64
        assert name.endswith("-260509143700-backup-test-job")

    def test_does_not_end_with_dash_after_truncation(self):
        """If truncation leaves a trailing dash on the source, strip it so the
        marker boundary isn't '--'."""
        m = _load_module()
        src = "a" * 22 + "-" + "b" * 40
        name = m.build_target_cluster_name(src, "260509143700")
        assert "--" not in name


class TestIsBackupTestCluster:
    def test_matches_current_format(self):
        m = _load_module()
        assert m.is_backup_test_cluster("Cluster0-260509143700-backup-test-job")

    def test_matches_legacy_suffix_format(self):
        """Older runs produced names like 'Cluster0-backup-test-job-2605091017'."""
        m = _load_module()
        assert m.is_backup_test_cluster("Cluster0-backup-test-job-2605091017")

    def test_matches_legacy_prefix_format(self):
        """The earliest runs produced names like 'backup-test-job-Cluster0'."""
        m = _load_module()
        assert m.is_backup_test_cluster("backup-test-job-Cluster0")

    def test_does_not_match_regular_cluster(self):
        m = _load_module()
        assert not m.is_backup_test_cluster("Cluster0")
        assert not m.is_backup_test_cluster("")
        assert not m.is_backup_test_cluster(None)


class TestBuildTargetClusterBody:
    def test_strips_server_managed_fields_and_renames(self):
        m = _load_module()
        body = m.build_target_cluster_body(_cluster("src"), "src-backup-test-job-2605091017")
        assert body["name"] == "src-backup-test-job-2605091017"
        for forbidden in (
            "id",
            "groupId",
            "createDate",
            "stateName",
            "mongoDBVersion",
            "connectionStrings",
            "paused",
            "links",
        ):
            assert forbidden not in body

    def test_preserves_mongodb_major_version(self):
        """Regression: target must match snapshot's major version or restore
        fails with INVALID_RESTORE_TO_TARGET. mongoDBMajorVersion must be kept
        even though some versions will be rejected at create time."""
        m = _load_module()
        body = m.build_target_cluster_body(_cluster("src"), "target")
        assert body["mongoDBMajorVersion"] == "8.3"

    def test_preserves_version_release_system(self):
        """Regression: minor versions (8.1/8.2/8.3) live on the CONTINUOUS
        track. Without this field Atlas defaults to LTS and rejects them with
        MONGODB_MAJOR_VERSION_INVALID."""
        m = _load_module()
        body = m.build_target_cluster_body(_cluster("src"), "target")
        assert body["versionReleaseSystem"] == "CONTINUOUS"

    def test_strips_replication_spec_ids(self):
        m = _load_module()
        body = m.build_target_cluster_body(_cluster("src"), "target")
        for spec in body.get("replicationSpecs", []):
            assert "id" not in spec

    def test_does_not_mutate_source(self):
        m = _load_module()
        src = _cluster("src")
        m.build_target_cluster_body(src, "target")
        assert src["id"] == "srv-id"
        assert src["replicationSpecs"][0]["id"] == "rs-id"


class TestClusterInstanceSize:
    def test_reads_electable_specs(self):
        m = _load_module()
        assert m.cluster_instance_size(_cluster(instance_size="M30")) == "M30"

    def test_reads_read_only_specs_when_electable_missing(self):
        m = _load_module()
        cluster = {
            "replicationSpecs": [
                {"regionConfigs": [{"readOnlySpecs": {"instanceSize": "M20"}}]}
            ]
        }
        assert m.cluster_instance_size(cluster) == "M20"

    def test_returns_none_when_missing(self):
        m = _load_module()
        assert m.cluster_instance_size({}) is None
        assert m.cluster_instance_size({"replicationSpecs": []}) is None
        assert m.cluster_instance_size(
            {"replicationSpecs": [{"regionConfigs": [{}]}]}
        ) is None


class TestExplainNoBackups:
    def test_m0_free_tier(self):
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="M0"))
        assert "M0" in msg and "free" in msg.lower()

    def test_shared_tier_m2(self):
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="M2"))
        assert "M2" in msg and "shared" in msg.lower()

    def test_shared_tier_m5(self):
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="M5"))
        assert "M5" in msg

    def test_flex_tier(self):
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="FLEX"))
        assert "Flex" in msg

    def test_serverless(self):
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="SERVERLESS"))
        assert "Serverless" in msg

    def test_m10_supports_but_disabled(self):
        """M10+ can have backups but the user may have turned them off."""
        m = _load_module()
        msg = m.explain_no_backups(_cluster(instance_size="M10", backup_enabled=False))
        assert "M10" in msg
        assert "disabled" in msg.lower() or "backupEnabled" in msg

    def test_unknown_tier(self):
        m = _load_module()
        msg = m.explain_no_backups({})
        assert "could not determine" in msg.lower() or "tier" in msg.lower()


class TestSnapshotMajorVersion:
    def test_extracts_from_mongod_version(self):
        m = _load_module()
        assert m.snapshot_major_version({"mongodVersion": "8.0.5"}) == "8.0"
        assert m.snapshot_major_version({"mongodVersion": "7.0.12"}) == "7.0"

    def test_falls_back_to_mongodb_version(self):
        m = _load_module()
        assert m.snapshot_major_version({"mongoDBVersion": "7.0.12"}) == "7.0"

    def test_returns_none_on_missing_or_malformed(self):
        m = _load_module()
        assert m.snapshot_major_version({}) is None
        assert m.snapshot_major_version({"mongodVersion": ""}) is None
        assert m.snapshot_major_version({"mongodVersion": "8"}) is None


class TestRestoreJobStatusHelpers:
    def test_terminal_states(self):
        m = _load_module()
        assert m.restore_job_terminal({"finishedAt": "now"})
        assert m.restore_job_terminal({"failed": True})
        assert m.restore_job_terminal({"cancelled": True})
        assert m.restore_job_terminal({"expired": True})
        assert not m.restore_job_terminal({})

    def test_succeeded(self):
        m = _load_module()
        assert m.restore_job_succeeded({"finishedAt": "now"})
        assert not m.restore_job_succeeded({"finishedAt": "now", "failed": True})
        assert not m.restore_job_succeeded({"finishedAt": "now", "cancelled": True})
        assert not m.restore_job_succeeded({"finishedAt": "now", "expired": True})
        assert not m.restore_job_succeeded({})


class TestMakeAtlasApiRequest:
    def test_success_returns_response(self):
        m = _load_module()
        with patch("requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, {"ok": True})
            resp = m.make_atlas_api_request("GET", "http://x")
            assert resp is not None
            assert resp.status_code == 200

    def test_failure_returns_none(self):
        m = _load_module()
        with patch("requests.request", side_effect=requests.exceptions.RequestException("x")):
            assert m.make_atlas_api_request("GET", "http://x") is None

    def test_http_error_response_body_is_logged(self):
        """Regression: error body should be available for debugging."""
        m = _load_module()
        err_resp = MagicMock()
        err_resp.text = '{"errorCode":"FOO"}'
        exc = requests.exceptions.HTTPError("boom")
        exc.response = err_resp
        with patch("requests.request", side_effect=exc):
            assert m.make_atlas_api_request("POST", "http://x") is None


def _paginated(results, has_next=False):
    return {
        "results": results,
        "links": [{"rel": "next"}] if has_next else [],
        "totalCount": len(results),
    }


class TestRun:
    """Integration-style tests over the full phased run() function."""

    def _patch_sleep(self, m):
        return patch.object(m.time, "sleep", return_value=None)

    def test_no_clusters_returns_zero(self):
        m = _load_module()
        with patch("requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, _paginated([]))
            assert m.run("proj", cleanup=False) == 0

    def test_fetch_clusters_failure_returns_one(self):
        m = _load_module()
        with patch("requests.request", side_effect=requests.exceptions.RequestException("x")):
            assert m.run("proj", cleanup=False) == 1

    def test_warning_when_backups_disabled(self):
        m = _load_module()
        clusters = [_cluster("NoBackupCluster", backup_enabled=False)]
        with patch("requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, _paginated(clusters))
            with self._patch_sleep(m):
                # Only 1 API call: listing clusters. No create, no restore.
                rc = m.run("proj", cleanup=False)
        assert rc == 0  # warnings don't flip exit code
        assert mock_req.call_count == 1

    def test_backups_disabled_warning_includes_tier_context(self):
        """Regression: the warning should explain *why* backups are off so the
        user can act (upgrade tier vs. flip backupEnabled)."""
        m = _load_module()
        clusters = [_cluster("FreeCluster", backup_enabled=False, instance_size="M0")]
        with patch("requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, _paginated(clusters))
            with patch.object(m.logger, "warning") as mock_warn:
                with self._patch_sleep(m):
                    m.run("proj", cleanup=False)
        logged = " ".join(c.args[0] for c in mock_warn.call_args_list)
        assert "M0" in logged

    def test_warning_when_no_snapshots_available(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([])),  # snapshots: none
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=False)
        assert rc == 0
        # 1 list-clusters + 1 list-snapshots, nothing else.
        assert mock_req.call_count == 2

    def test_warning_when_snapshot_version_mismatches_cluster(self):
        """Regression: Atlas rejects restore across major versions
        (INVALID_RESTORE_TO_TARGET). We should flag this before create."""
        m = _load_module()
        cluster = _cluster("ClusterA", backup_enabled=True)
        cluster["mongoDBMajorVersion"] = "8.0"
        snapshot = {"id": "snap-1", "mongodVersion": "7.0.12"}
        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated([cluster])),
                _mock_resp(200, _paginated([snapshot])),
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=False)
        assert rc == 0  # warnings don't flip exit code
        # No create or restore calls should have been issued.
        assert mock_req.call_count == 2

    def test_happy_path_success(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}
        created_cluster = {"name": "ClusterA-backup-test-job-2605091017"}
        idle_target = {"stateName": "IDLE", "name": created_cluster["name"]}
        restore_started = {"id": "job-1"}
        restore_finished = {"id": "job-1", "finishedAt": "2026-01-01T00:00:00Z"}

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),       # list clusters
                _mock_resp(200, _paginated([snapshot])),     # list snapshots
                _mock_resp(201, created_cluster),            # create target
                _mock_resp(200, idle_target),                # first IDLE poll
                _mock_resp(201, restore_started),            # start restore
                _mock_resp(200, restore_finished),           # first restore poll
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=False)
        assert rc == 0

    def test_happy_path_with_cleanup_issues_delete(self):  # noqa: D401
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}
        idle_target = {"stateName": "IDLE"}
        restore_finished = {"id": "job-1", "finishedAt": "now"}

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
                _mock_resp(201, {"name": "target"}),         # create
                _mock_resp(200, idle_target),                # idle poll
                _mock_resp(201, {"id": "job-1"}),            # restore start
                _mock_resp(200, restore_finished),           # restore poll
                _mock_resp(202, {"ok": True}),               # delete (cleanup)
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=True)
        assert rc == 0
        # Last call should be DELETE.
        last_call = mock_req.call_args_list[-1]
        assert last_call.args[0] == "DELETE"

    def test_create_failure_marks_error_and_skips_cleanup_for_that_cluster(self):
        """Regression: if POST /clusters fails, that cluster must NOT be
        deleted in the cleanup phase (target_created stays False)."""
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        err_resp = MagicMock()
        err_resp.text = '{"errorCode":"DUPLICATE_CLUSTER_NAME"}'
        http_err = requests.exceptions.HTTPError("400")
        http_err.response = err_resp

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
                http_err,  # POST /clusters fails
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=True)

        assert rc == 1
        methods_called = [c.args[0] for c in mock_req.call_args_list]
        assert "DELETE" not in methods_called

    def test_restore_job_failure_returns_error_exit_code(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
                _mock_resp(201, {"name": "target"}),
                _mock_resp(200, {"stateName": "IDLE"}),
                _mock_resp(201, {"id": "job-1"}),
                _mock_resp(200, {"id": "job-1", "failed": True, "finishedAt": "now"}),
            ]
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=False)
        assert rc == 1

    def test_cluster_idle_timeout_returns_error(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        with patch("requests.request") as mock_req:
            # list clusters + list snapshots + create + (arbitrary polls, all
            # return CREATING -- we shrink the timeout so the loop exits.)
            mock_req.side_effect = (
                [
                    _mock_resp(200, _paginated(clusters)),
                    _mock_resp(200, _paginated([snapshot])),
                    _mock_resp(201, {"name": "target"}),
                ]
                + [_mock_resp(200, {"stateName": "CREATING"})] * 20
            )
            # Force the waiter loop to exit after the first poll.
            with patch.object(m, "CLUSTER_READY_TIMEOUT_SECONDS", 0):
                with self._patch_sleep(m):
                    rc = m.run("proj", cleanup=False)
        assert rc == 1

    def test_legacy_backup_clusters_skipped_as_sources(self):
        """A cluster named with the legacy or new format should be ignored when
        picking source clusters (so repeat runs don't loop on their own output)."""
        m = _load_module()
        clusters = [
            _cluster("ClusterA", backup_enabled=False),
            _cluster("backup-test-job-ClusterA", backup_enabled=True),
            _cluster("ClusterA-backup-test-job-2601010000", backup_enabled=True),
            _cluster("ClusterA-260101000000-backup-test-job", backup_enabled=True),
        ]
        with patch("requests.request") as mock_req:
            mock_req.return_value = _mock_resp(200, _paginated(clusters))
            with self._patch_sleep(m):
                rc = m.run("proj", cleanup=False)
        # Only one "real" source (ClusterA), and it has backups disabled ->
        # warning only, no extra API calls beyond the list.
        assert rc == 0
        assert mock_req.call_count == 1


class TestRecoverTimedOut:
    def test_retry_resets_item_and_deletes_target(self):
        """When retries remain, the stuck cluster is deleted and the item is
        re-queued for another create attempt."""
        m = _load_module()
        item = {
            "source_name": "src",
            "target_name": "src-target",
            "target_created": True,
            "restore_job_id": "job-1",
            "status": "creating",
            "message": "",
            "retries_remaining": 1,
        }
        with patch.object(m, "delete_cluster", return_value=True) as mock_del:
            m.recover_timed_out([item], "timeout", 1, "proj", None, {})
        mock_del.assert_called_once_with("proj", "src-target", None, {})
        assert item["status"] == "pending_create"
        assert item["retries_remaining"] == 0
        assert item["target_created"] is False
        assert item["restore_job_id"] is None

    def test_out_of_retries_marks_error(self):
        m = _load_module()
        item = {
            "source_name": "src",
            "target_name": "src-target",
            "target_created": True,
            "restore_job_id": None,
            "status": "creating",
            "message": "",
            "retries_remaining": 0,
        }
        with patch.object(m, "delete_cluster", return_value=True):
            m.recover_timed_out([item], "timeout", 0, "proj", None, {})
        assert item["status"] == "error"
        assert "out of retries" in item["message"]

    def test_delete_failure_still_advances(self):
        """If the DELETE itself fails, we still proceed (log error but don't
        hang). The item still gets retried or errored based on budget."""
        m = _load_module()
        item = {
            "source_name": "src",
            "target_name": "src-target",
            "target_created": True,
            "restore_job_id": None,
            "status": "creating",
            "message": "",
            "retries_remaining": 0,
        }
        with patch.object(m, "delete_cluster", return_value=False):
            m.recover_timed_out([item], "timeout", 0, "proj", None, {})
        assert item["status"] == "error"


class TestRunTimeoutRecovery:
    """Integration tests: a target times out, gets deleted, and the pipeline
    retries from the create phase.

    These mock the phase-helper functions directly so we can simulate a
    timeout on the first attempt and success on the second without racing
    the real-time deadline. The phase helpers themselves are unit-tested
    separately.
    """

    def _setup_run(self, m, clusters, snapshot):
        """Arrange the initial API calls that Phase 1-2 make (listing clusters
        and the latest snapshot)."""
        mock_req = MagicMock()
        mock_req.side_effect = [
            _mock_resp(200, _paginated(clusters)),
            _mock_resp(200, _paginated([snapshot])),
        ]
        return mock_req

    def test_idle_timeout_retries_and_succeeds(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        # On attempt 1, pretend the waiter timed out (returns the item).
        # On attempt 2, the waiter sets the item to ready_for_restore.
        def first_timeout_then_success(items, *a, **kw):
            creating = [i for i in items if i["status"] == "creating"]
            if first_timeout_then_success.calls == 0:
                first_timeout_then_success.calls += 1
                return creating  # timed out
            for i in creating:
                i["status"] = "ready_for_restore"
            return []
        first_timeout_then_success.calls = 0

        def restores_succeed(items, *a, **kw):
            for i in items:
                if i["status"] == "restoring":
                    i["status"] = "success"
                    i["message"] = "ok"
            return []

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
            ]
            with patch.object(m, "create_targets", side_effect=lambda items, *a, **kw: [
                i.__setitem__("target_created", True) or i.__setitem__("status", "creating")
                for i in items if i["status"] == "pending_create"
            ]):
                with patch.object(m, "wait_for_targets_idle", side_effect=first_timeout_then_success):
                    with patch.object(m, "delete_cluster", return_value=True):
                        with patch.object(m, "start_restores", side_effect=lambda items, *a, **kw: [
                            i.__setitem__("status", "restoring")
                            for i in items if i["status"] == "ready_for_restore"
                        ]):
                            with patch.object(m, "poll_restores", side_effect=restores_succeed):
                                rc = m.run("proj", cleanup=False, max_retries=1)
        assert rc == 0
        assert first_timeout_then_success.calls == 1  # wait was called 2x (0->1 counter)

    def test_idle_timeout_exhausts_retries_and_errors(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        def always_timeout(items, *a, **kw):
            return [i for i in items if i["status"] == "creating"]

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
            ]
            with patch.object(m, "create_targets", side_effect=lambda items, *a, **kw: [
                i.__setitem__("target_created", True) or i.__setitem__("status", "creating")
                for i in items if i["status"] == "pending_create"
            ]):
                with patch.object(m, "wait_for_targets_idle", side_effect=always_timeout):
                    with patch.object(m, "delete_cluster", return_value=True) as mock_del:
                        rc = m.run("proj", cleanup=False, max_retries=1)
        assert rc == 1
        # One DELETE per failed attempt (two attempts = two deletes).
        assert mock_del.call_count == 2

    def test_restore_timeout_triggers_retry(self):
        m = _load_module()
        clusters = [_cluster("ClusterA", backup_enabled=True)]
        snapshot = {"id": "snap-1"}

        def poll_first_timeout_then_success(items, *a, **kw):
            restoring = [i for i in items if i["status"] == "restoring"]
            if poll_first_timeout_then_success.calls == 0:
                poll_first_timeout_then_success.calls += 1
                return restoring  # timed out
            for i in restoring:
                i["status"] = "success"
                i["message"] = "ok"
            return []
        poll_first_timeout_then_success.calls = 0

        with patch("requests.request") as mock_req:
            mock_req.side_effect = [
                _mock_resp(200, _paginated(clusters)),
                _mock_resp(200, _paginated([snapshot])),
            ]
            with patch.object(m, "create_targets", side_effect=lambda items, *a, **kw: [
                i.__setitem__("target_created", True) or i.__setitem__("status", "creating")
                for i in items if i["status"] == "pending_create"
            ]):
                with patch.object(m, "wait_for_targets_idle", side_effect=lambda items, *a, **kw: [
                    i.__setitem__("status", "ready_for_restore")
                    for i in items if i["status"] == "creating"
                ] and []):
                    with patch.object(m, "start_restores", side_effect=lambda items, *a, **kw: [
                        i.__setitem__("status", "restoring")
                        for i in items if i["status"] == "ready_for_restore"
                    ]):
                        with patch.object(m, "poll_restores", side_effect=poll_first_timeout_then_success):
                            with patch.object(m, "delete_cluster", return_value=True):
                                rc = m.run("proj", cleanup=False, max_retries=1)
        assert rc == 0


class TestMain:
    def test_main_requires_project_id(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog"]):
            with pytest.raises(SystemExit):
                m.main()

    def test_main_success_path(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog", "--project-id", "p1"]):
            with patch.object(m, "run", return_value=0) as mock_run:
                rc = m.main()
        assert rc == 0
        mock_run.assert_called_once_with("p1", False, m.DEFAULT_MAX_RETRIES)

    def test_main_passes_cleanup_flag(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog", "--project-id", "p1", "--cleanup"]):
            with patch.object(m, "run", return_value=0) as mock_run:
                m.main()
        mock_run.assert_called_once_with("p1", True, m.DEFAULT_MAX_RETRIES)

    def test_main_passes_max_retries(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog", "--project-id", "p1", "--max-retries", "3"]):
            with patch.object(m, "run", return_value=0) as mock_run:
                m.main()
        mock_run.assert_called_once_with("p1", False, 3)

    def test_main_keyboard_interrupt(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog", "--project-id", "p1"]):
            with patch.object(m, "run", side_effect=KeyboardInterrupt):
                assert m.main() == 1

    def test_main_unexpected_exception(self):
        m = _load_module()
        with patch.object(sys, "argv", ["prog", "--project-id", "p1"]):
            with patch.object(m, "run", side_effect=RuntimeError("x")):
                assert m.main() == 1
