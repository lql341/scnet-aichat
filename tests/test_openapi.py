#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "scnet_aichat_openapi", ROOT / "scripts" / "scnet-openapi.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, data):
        self.body = json.dumps(
            {"code": "0", "msg": "success", "data": data}
        ).encode("utf-8")
        self.headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


class OpenAPIHelperTests(unittest.TestCase):
    def test_signature_matches_documented_algorithm(self):
        message = '{"accessKey":"ak","timestamp":"1764597591","user":"alice"}'
        expected = hmac.new(
            b"secret", message.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(
            MODULE.canonical_signature("ak", "1764597591", "alice", "secret"),
            expected,
        )

    def test_service_endpoint_does_not_duplicate_service_name(self):
        self.assertEqual(
            MODULE.service_endpoint(
                "https://example.test/hpc", "hpc", "/openapi/v2/cluster"
            ),
            "https://example.test/hpc/openapi/v2/cluster",
        )

    def test_metadata_is_private_and_contains_no_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"SCNET_AICHAT_CONFIG_DIR": directory}
        ):
            MODULE.save_metadata(
                {
                    "region_id": "123",
                    "username": "alice",
                    "home_path": "/public/home/alice",
                }
            )
            path = MODULE.metadata_path()
            mode = stat.S_IMODE(path.stat().st_mode)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(mode, 0o600)
            self.assertNotIn("access_key", data)
            self.assertNotIn("secret_key", data)
            self.assertEqual(MODULE.backend_path().read_text().strip(), "openapi")

    def test_environment_credentials_take_precedence(self):
        with patch.dict(
            os.environ,
            {
                "SCNET_OPENAPI_USER": "alice",
                "SCNET_OPENAPI_ACCESS_KEY": "ak",
                "SCNET_OPENAPI_SECRET_KEY": "secret",
            },
            clear=False,
        ):
            credentials, provider = MODULE.load_credentials()
        self.assertEqual(provider, "environment")
        self.assertEqual(credentials["user"], "alice")

    def test_auth_center_and_scheduler_discovery(self):
        base = "https://mock.scnet.test"

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 5)
            if request.full_url == base + "/api/user/v3/tokens":
                return FakeResponse(
                    [
                        {
                            "clusterId": "456",
                            "clusterName": "test-region",
                            "token": "region-token",
                        }
                    ]
                )
            if request.full_url == base + "/center":
                return FakeResponse(
                    {
                        "clusterUserInfo": {
                            "userName": "alice",
                            "homePath": "/public/home/alice",
                        },
                        "hpcUrls": [{"enable": "true", "url": base + "/hpc"}],
                        "efileUrls": [{"enable": "true", "url": base + "/efile"}],
                    }
                )
            if request.full_url == base + "/hpc/openapi/v2/cluster":
                return FakeResponse([{"id": 123, "text": "slurm"}])
            raise AssertionError(request.full_url)

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "SCNET_AICHAT_CONFIG_DIR": directory,
                "SCNET_OPENAPI_USER": "alice",
                "SCNET_OPENAPI_ACCESS_KEY": "ak",
                "SCNET_OPENAPI_SECRET_KEY": "secret",
                "SCNET_OPENAPI_AUTH_BASE": base,
                "SCNET_OPENAPI_CENTER_URL": base + "/center",
            },
            clear=False,
        ), patch.object(MODULE, "urlopen", side_effect=fake_urlopen):
            context = MODULE.Client(timeout=5).context("456", None)
        self.assertEqual(context["home_path"], "/public/home/alice")
        self.assertEqual(context["scheduler_id"], "123")
        self.assertEqual(context["username"], "alice")

    def test_submit_uses_basic_command_payload_without_credentials(self):
        client = MODULE.Client(timeout=5)
        captured = {}

        def request(method, url, **kwargs):
            captured.update({"method": method, "url": url, **kwargs})
            return "148"

        client.request = request
        job_id = client.submit(
            {
                "hpc_url": "https://example.test/hpc",
                "token": "region-token",
                "scheduler_id": "123",
                "region_id": "456",
            },
            Namespace(
                command="bash -l worker.slurm",
                name="scnet-aichat-14b",
                work_dir="/public/home/alice/request",
                queue="debug",
                cpus=8,
                dcus=1,
                memory="27gb",
                walltime="02:00:00",
                stdout="/public/home/alice/request/slurm-%j.out",
                stderr="/public/home/alice/request/slurm-%j.err",
            ),
        )
        self.assertEqual(job_id, "148")
        body = captured["json_body"]["mapAppJobInfo"]
        self.assertEqual(body["GAP_NDCU"], "1")
        self.assertEqual(body["GAP_NPROC"], "8")
        self.assertEqual(body["GAP_JOB_MEM"], "27GB")
        self.assertNotIn("region-token", json.dumps(captured["json_body"]))

    def test_submit_rejects_empty_job_id(self):
        client = MODULE.Client(timeout=5)
        client.last_message = "success"
        client.request = lambda *args, **kwargs: ""
        with self.assertRaises(MODULE.OpenAPIError):
            client.submit(
                {
                    "hpc_url": "https://example.test/hpc",
                    "token": "region-token",
                    "scheduler_id": "123",
                    "region_id": "456",
                },
                Namespace(
                    command="echo ok",
                    name="probe",
                    work_dir="/public/home/alice/probe",
                    queue="debug",
                    cpus=1,
                    dcus=1,
                    memory="1gb",
                    walltime="00:05:00",
                    stdout="/public/home/alice/probe/std.out.%j",
                    stderr="/public/home/alice/probe/std.err.%j",
                ),
            )

    def test_path_redaction(self):
        self.assertEqual(
            MODULE.redact_path(
                "/public/home/alice/work/std.out.1", "/public/home/alice"
            ),
            "$REMOTE_HOME/work/std.out.1",
        )

    def test_kunshan_is_the_builtin_default_region(self):
        client = MODULE.Client(timeout=5)
        client._regions = [
            {
                "clusterId": "11250",
                "clusterName": "Kunshan",
                "token": "one",
            },
            {
                "clusterId": "20091",
                "clusterName": "Future region",
                "token": "two",
            },
        ]
        self.assertEqual(
            client.select_region(MODULE.DEFAULT_REGION_ID)["clusterId"],
            "11250",
        )

    def test_submit_parser_keeps_operation_and_job_command_separate(self):
        args = MODULE.build_parser().parse_args(
            [
                "submit",
                "--name",
                "probe",
                "--command",
                "echo ok",
                "--work-dir",
                "/work",
                "--queue",
                "debug",
                "--cpus",
                "1",
                "--dcus",
                "1",
                "--memory",
                "1gb",
                "--walltime",
                "00:05:00",
                "--stdout",
                "/work/out",
                "--stderr",
                "/work/err",
            ]
        )
        self.assertEqual(args.operation, "submit")
        self.assertEqual(args.command, "echo ok")

    def test_local_config_path_is_home_relative(self):
        path = Path.home() / ".config" / "scnet-aichat" / "openapi.json"
        self.assertEqual(
            MODULE.display_local_path(path),
            "~/.config/scnet-aichat/openapi.json",
        )


if __name__ == "__main__":
    unittest.main()
