#!/usr/bin/env python3
"""SCNet OpenAPI helper for scnet-aichat.

The helper intentionally uses only the Python standard library. Long-lived
AK/SK credentials are loaded from environment variables, macOS Keychain, or
Linux Secret Service. Region tokens are fetched per invocation and never
persisted.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import mimetypes
import os
import platform
import posixpath
import select
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SERVICE = "scnet-hpc-openapi"
USER_AGENT = "scnet-aichat/1"
DEFAULT_REGION_ID = "11250"
STATUS_MAP = {
    "statR": "RUNNING",
    "statQ": "PENDING",
    "statH": "HELD",
    "statS": "SUSPENDED",
    "statE": "EXITING",
    "statF": "FAILED",
    "statC": "COMPLETED",
    "statW": "WAITING",
    "statX": "OTHER",
}


class OpenAPIError(RuntimeError):
    """Bounded user-facing OpenAPI failure."""


def config_root() -> Path:
    override = os.environ.get("SCNET_AICHAT_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base).expanduser() / "scnet-aichat"
    return Path.home() / ".config" / "scnet-aichat"


def metadata_path() -> Path:
    return config_root() / "openapi.json"


def backend_path() -> Path:
    return config_root() / "backend"


def load_metadata() -> dict[str, Any]:
    try:
        data = json.loads(metadata_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def save_metadata(data: Mapping[str, Any]) -> None:
    atomic_write(
        metadata_path(),
        json.dumps(dict(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    atomic_write(backend_path(), "openapi\n")


def valid_credentials(data: Any) -> bool:
    return isinstance(data, dict) and all(
        isinstance(data.get(key), str) and data[key]
        for key in ("user", "access_key", "secret_key")
    )


def environment_credentials() -> dict[str, str] | None:
    data = {
        "user": os.environ.get("SCNET_OPENAPI_USER", ""),
        "access_key": os.environ.get("SCNET_OPENAPI_ACCESS_KEY", ""),
        "secret_key": os.environ.get("SCNET_OPENAPI_SECRET_KEY", ""),
    }
    return data if valid_credentials(data) else None


def secure_store_name() -> str | None:
    if platform.system() == "Darwin" and shutil.which("security"):
        return "macOS Keychain"
    if shutil.which("secret-tool"):
        return "Secret Service"
    return None


def load_secure_credentials() -> dict[str, str] | None:
    provider = secure_store_name()
    if provider == "macOS Keychain":
        command = ["security", "find-generic-password", "-s", SERVICE, "-w"]
    elif provider == "Secret Service":
        command = ["secret-tool", "lookup", "service", SERVICE]
    else:
        return None
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return data if valid_credentials(data) else None


def load_credentials() -> tuple[dict[str, str] | None, str | None]:
    data = environment_credentials()
    if data:
        return data, "environment"
    data = load_secure_credentials()
    if data:
        return data, secure_store_name()
    return None, None


def store_credentials(user: str, access_key: str, secret_key: str) -> str:
    data = {"user": user, "access_key": access_key, "secret_key": secret_key}
    if not valid_credentials(data):
        raise OpenAPIError("OpenAPI credentials are incomplete")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    provider = secure_store_name()
    if provider == "macOS Keychain":
        completed = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                SERVICE,
                "-a",
                user,
                "-w",
                payload,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    elif provider == "Secret Service":
        completed = subprocess.run(
            [
                "secret-tool",
                "store",
                "--label=SCNet OpenAPI",
                "service",
                SERVICE,
                "user",
                user,
            ],
            input=payload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    else:
        raise OpenAPIError(
            "no supported secure store; use SCNET_OPENAPI_USER, "
            "SCNET_OPENAPI_ACCESS_KEY, and SCNET_OPENAPI_SECRET_KEY"
        )
    if completed.returncode != 0:
        raise OpenAPIError(
            completed.stderr.strip() or f"failed to write {provider}"
        )
    return str(provider)


def delete_credentials() -> tuple[bool, str | None]:
    provider = secure_store_name()
    if provider == "macOS Keychain":
        command = ["security", "delete-generic-password", "-s", SERVICE]
    elif provider == "Secret Service":
        command = ["secret-tool", "clear", "service", SERVICE]
    else:
        return False, None
    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True, provider
    if load_secure_credentials() is None:
        return False, provider
    raise OpenAPIError(
        completed.stderr.strip() or f"failed to clear {provider}"
    )


def canonical_signature(
    access_key: str, timestamp: str, user: str, secret_key: str
) -> str:
    message = json.dumps(
        {"accessKey": access_key, "timestamp": timestamp, "user": user},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def service_endpoint(base_url: str, service: str, suffix: str) -> str:
    split = urlsplit(base_url.rstrip("/"))
    path = split.path.rstrip("/")
    service_part = f"/{service}"
    if not path.endswith(service_part):
        path += service_part
    path += "/" + suffix.lstrip("/")
    return urlunsplit((split.scheme, split.netloc, path, "", ""))


class Client:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._regions: list[dict[str, Any]] | None = None
        self._centers: dict[str, dict[str, Any]] = {}
        self.last_message = ""

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        json_body: Any | None = None,
        form: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if headers:
            request_headers.update(headers)
        if token:
            request_headers["token"] = token
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urlencode(form).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = Request(url, data=data, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise OpenAPIError(
                f"HTTP {exc.code} from SCNet OpenAPI"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenAPIError(f"SCNet OpenAPI request failed: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAPIError("SCNet OpenAPI returned a non-JSON response") from exc
        if not isinstance(payload, dict):
            raise OpenAPIError("SCNet OpenAPI response must be a JSON object")
        code = str(payload.get("code", ""))
        self.last_message = str(payload.get("msg") or "")
        if code != "0":
            raise OpenAPIError(
                f"SCNet OpenAPI error {code}: "
                f"{payload.get('msg') or 'unknown error'}"
            )
        return payload.get("data")

    def regions(self) -> list[dict[str, Any]]:
        if self._regions is not None:
            return self._regions
        direct_token = os.environ.get("SCNET_OPENAPI_TOKEN")
        if direct_token:
            region_id = os.environ.get(
                "SCNET_OPENAPI_REGION_ID", DEFAULT_REGION_ID
            )
            self._regions = [
                {
                    "clusterId": region_id,
                    "clusterName": os.environ.get(
                        "SCNET_OPENAPI_REGION_NAME", "configured"
                    ),
                    "token": direct_token,
                }
            ]
            return self._regions
        credentials, _ = load_credentials()
        if not credentials:
            raise OpenAPIError(
                "OpenAPI credentials are not configured; run "
                "`scnet-aichat setup new` or set SCNET_OPENAPI_USER, "
                "SCNET_OPENAPI_ACCESS_KEY, and SCNET_OPENAPI_SECRET_KEY"
            )
        timestamp = str(int(time.time()))
        signature = canonical_signature(
            credentials["access_key"],
            timestamp,
            credentials["user"],
            credentials["secret_key"],
        )
        auth_base = os.environ.get(
            "SCNET_OPENAPI_AUTH_BASE", "https://api.scnet.cn"
        )
        data = self.request(
            "POST",
            auth_base.rstrip("/") + "/api/user/v3/tokens",
            headers={
                "user": credentials["user"],
                "accessKey": credentials["access_key"],
                "signature": signature,
                "timestamp": timestamp,
            },
        )
        if not isinstance(data, list):
            raise OpenAPIError("token endpoint returned an unexpected data shape")
        self._regions = [item for item in data if isinstance(item, dict)]
        return self._regions

    def select_region(self, requested: str | None) -> dict[str, Any]:
        usable = [
            item
            for item in self.regions()
            if str(item.get("clusterId", "")) != "0" and item.get("token")
        ]
        if requested:
            for item in usable:
                if str(item.get("clusterId")) == requested or str(
                    item.get("clusterName")
                ) == requested:
                    return item
            raise OpenAPIError(f"OpenAPI region {requested!r} is not available")
        if len(usable) == 1:
            return usable[0]
        raise OpenAPIError(
            "multiple OpenAPI regions are available; run `scnet-aichat setup new`"
        )

    def center(self, region: Mapping[str, Any]) -> dict[str, Any]:
        region_id = str(region.get("clusterId", ""))
        if region_id not in self._centers:
            center_url = os.environ.get(
                "SCNET_OPENAPI_CENTER_URL",
                "https://www.scnet.cn/ac/openapi/v2/center",
            )
            data = self.request("GET", center_url, token=str(region["token"]))
            if not isinstance(data, dict):
                raise OpenAPIError(
                    "center endpoint returned an unexpected data shape"
                )
            self._centers[region_id] = data
        return self._centers[region_id]

    @staticmethod
    def enabled_url(center: Mapping[str, Any], field: str) -> str:
        values = center.get(field)
        if not isinstance(values, list):
            raise OpenAPIError(f"center response has no {field}")
        for item in values:
            if not isinstance(item, dict):
                continue
            enabled = str(item.get("enable", "true")).lower() == "true"
            if enabled and item.get("url"):
                return str(item["url"])
        raise OpenAPIError(f"center response has no enabled URL in {field}")

    def context(
        self, requested_region: str | None, requested_scheduler: str | None
    ) -> dict[str, Any]:
        saved = load_metadata()
        requested_region = (
            requested_region
            or str(saved.get("region_id") or "")
            or None
        )
        if not requested_region:
            raise OpenAPIError(
                "OpenAPI region is not selected; run `scnet-aichat setup new`"
            )
        region = self.select_region(requested_region)
        center = self.center(region)
        token = str(region["token"])
        hpc_url = self.enabled_url(center, "hpcUrls")
        efile_url = self.enabled_url(center, "efileUrls")
        schedulers = self.request(
            "GET",
            service_endpoint(hpc_url, "hpc", "/openapi/v2/cluster"),
            token=token,
        )
        if not isinstance(schedulers, list):
            raise OpenAPIError("cluster endpoint returned an unexpected data shape")
        requested_scheduler = (
            requested_scheduler
            or str(saved.get("scheduler_id") or "")
            or None
        )
        selected: Mapping[str, Any] | None = None
        if requested_scheduler:
            selected = next(
                (
                    item
                    for item in schedulers
                    if str(item.get("id")) == requested_scheduler
                ),
                None,
            )
            if selected is None:
                raise OpenAPIError(
                    f"scheduler {requested_scheduler!r} is not available"
                )
        elif len(schedulers) == 1:
            selected = schedulers[0]
        else:
            raise OpenAPIError(
                "multiple schedulers are available; run `scnet-aichat setup modify`"
            )
        user_info = center.get("clusterUserInfo") or {}
        username = (
            os.environ.get("SCNET_OPENAPI_USERNAME")
            or user_info.get("userName")
            or saved.get("username")
        )
        home_path = user_info.get("homePath") or saved.get("home_path")
        if not username or not home_path:
            raise OpenAPIError(
                "OpenAPI did not return the region username or home path"
            )
        return {
            "region_id": str(region.get("clusterId") or ""),
            "region_name": region.get("clusterName"),
            "token": token,
            "center": center,
            "hpc_url": hpc_url,
            "efile_url": efile_url,
            "scheduler_id": str(selected["id"]),
            "scheduler_name": selected.get("text"),
            "username": str(username),
            "home_path": str(home_path),
        }

    def discover_contexts(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for region in self.regions():
            region_id = str(region.get("clusterId", ""))
            if region_id == "0" or not region.get("token"):
                continue
            try:
                center = self.center(region)
                hpc_url = self.enabled_url(center, "hpcUrls")
                self.enabled_url(center, "efileUrls")
            except OpenAPIError:
                continue
            schedulers = self.request(
                "GET",
                service_endpoint(hpc_url, "hpc", "/openapi/v2/cluster"),
                token=str(region["token"]),
            )
            if not isinstance(schedulers, list) or not schedulers:
                continue
            user_info = center.get("clusterUserInfo") or {}
            result.append(
                {
                    "region_id": region_id,
                    "region_name": region.get("clusterName"),
                    "username": user_info.get("userName"),
                    "home_path": user_info.get("homePath"),
                    "schedulers": [
                        {
                            "id": str(item.get("id", "")),
                            "name": item.get("text"),
                        }
                        for item in schedulers
                        if isinstance(item, dict)
                    ],
                }
            )
        return result

    def mkdir(self, context: Mapping[str, Any], path: str) -> None:
        ensure_absolute_path(path)
        url = (
            service_endpoint(
                str(context["efile_url"]), "efile", "/openapi/v2/file/mkdir"
            )
            + "?"
            + urlencode({"path": path, "createParents": "true"})
        )
        self.request(
            "POST",
            url,
            token=str(context["token"]),
            json_body={},
        )

    def upload(
        self,
        context: Mapping[str, Any],
        local_path: Path,
        remote_directory: str,
        *,
        cover: bool,
    ) -> None:
        if not local_path.is_file():
            raise OpenAPIError(f"local file does not exist: {local_path}")
        ensure_absolute_path(remote_directory)
        boundary = "----scnet-aichat-" + uuid.uuid4().hex
        fields = {
            "cover": "cover" if cover else "uncover",
            "path": remote_directory,
        }
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        safe_name = (
            local_path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        )
        content_type = (
            mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        )
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{safe_name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
            + local_path.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        request = Request(
            service_endpoint(
                str(context["efile_url"]), "efile", "/openapi/v2/file/upload"
            ),
            data=b"".join(parts),
            method="POST",
            headers={
                "token": str(context["token"]),
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            raise OpenAPIError(f"OpenAPI upload failed: {exc}") from exc
        if not isinstance(payload, dict) or str(payload.get("code", "")) != "0":
            raise OpenAPIError(
                f"SCNet OpenAPI error {payload.get('code')}: {payload.get('msg')}"
            )

    def submit(self, context: Mapping[str, Any], args: argparse.Namespace) -> str:
        ensure_absolute_path(args.work_dir)
        body = {
            "strJobManagerID": str(context["scheduler_id"]),
            "mapAppJobInfo": {
                "GAP_CMD_FILE": args.command,
                "GAP_NNODE": "1",
                "GAP_NODE_STRING": "",
                "GAP_SUBMIT_TYPE": "cmd",
                "GAP_JOB_NAME": args.name,
                "GAP_WORK_DIR": args.work_dir,
                "GAP_QUEUE": args.queue,
                "GAP_NPROC": str(args.cpus),
                "GAP_PPN": "",
                "GAP_NGPU": "",
                "GAP_NDCU": str(args.dcus),
                "GAP_JOB_MEM": str(args.memory).upper(),
                "GAP_WALL_TIME": args.walltime,
                "GAP_EXCLUSIVE": "",
                "GAP_APPNAME": "BASE",
                "GAP_MULTI_SUB": "",
                "GAP_STD_OUT_FILE": args.stdout,
                "GAP_STD_ERR_FILE": args.stderr,
                "GAP_SCHEDULER_OPT_WEB": "",
                "GAP_CLUSTER_ID": str(context["region_id"]),
            },
        }
        data = self.request(
            "POST",
            service_endpoint(
                str(context["hpc_url"]),
                "hpc",
                "/openapi/v2/apptemplates/BASIC/BASE/job",
            ),
            token=str(context["token"]),
            json_body=body,
        )
        if isinstance(data, dict):
            job_id = str(data.get("jobId") or data.get("job_id") or "")
        else:
            job_id = str(data or "")
        if not job_id.isdigit():
            detail = f": {self.last_message}" if self.last_message else ""
            raise OpenAPIError(
                "SCNet accepted the submit request but returned no numeric job ID"
                + detail
            )
        return job_id

    def job(self, context: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        data = self.request(
            "GET",
            service_endpoint(
                str(context["hpc_url"]),
                "hpc",
                f"/openapi/v2/jobs/{quote(job_id)}",
            ),
            token=str(context["token"]),
        )
        if not isinstance(data, dict):
            raise OpenAPIError("job endpoint returned an unexpected data shape")
        raw_state = data.get("jobStatus") or data.get("state") or ""
        return {
            "job_id": str(data.get("jobId") or job_id),
            "name": data.get("jobName") or data.get("name"),
            "state": STATUS_MAP.get(str(raw_state), str(raw_state)),
            "raw_state": raw_state,
            "queue": data.get("queue"),
            "elapsed": data.get("jobRunTime"),
            "exit_code": data.get("exitCode"),
            "reason": data.get("reason"),
            "work_dir": data.get("workDir"),
            "stdout": data.get("outputPath"),
            "stderr": data.get("errorPath"),
        }

    def cancel(self, context: Mapping[str, Any], job_id: str) -> None:
        method = os.environ.get("SCNET_OPENAPI_CANCEL_METHOD", "5")
        self.request(
            "DELETE",
            service_endpoint(
                str(context["hpc_url"]), "hpc", "/openapi/v2/jobs"
            ),
            token=str(context["token"]),
            form={
                "jobMethod": method,
                "strJobInfoMap": (
                    f"{context['scheduler_id']},{context['username']}:{job_id}:"
                ),
            },
        )

    def read_file(self, context: Mapping[str, Any], path: str) -> bytes:
        ensure_absolute_path(path)
        url = (
            service_endpoint(
                str(context["efile_url"]), "efile", "/openapi/v2/file/download"
            )
            + "?"
            + urlencode({"path": path})
        )
        request = Request(
            url,
            method="GET",
            headers={"token": str(context["token"]), "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                content = response.read()
        except HTTPError as exc:
            raise OpenAPIError(f"remote file is unavailable: HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenAPIError(f"OpenAPI download failed: {exc}") from exc
        if "application/json" in content_type:
            try:
                payload = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and str(payload.get("code", "0")) != "0":
                raise OpenAPIError(
                    f"SCNet OpenAPI error {payload.get('code')}: "
                    f"{payload.get('msg')}"
                )
        return content


def ensure_absolute_path(path: str) -> None:
    if (
        not path.startswith("/")
        or "\n" in path
        or "\r" in path
        or "\x00" in path
    ):
        raise OpenAPIError("remote path must be a safe absolute path")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def choose(prompt: str, labels: list[str], default: int = 1) -> int:
    if (
        sys.stdin.isatty()
        and sys.stdout.isatty()
        and os.name == "posix"
        and os.environ.get("TERM", "") != "dumb"
    ):
        return choose_interactive(prompt, labels, default)

    print(prompt)
    for index, label in enumerate(labels, 1):
        marker = "*" if index == default else " "
        print(f"  {marker} {index}. {label}")
    print(f"请输入 1-{len(labels)} 的数字并按 Enter。")
    print(f"直接按 Enter 使用带 * 的默认项 {default}。")
    answer = ask("选择", str(default))
    try:
        selected = int(answer)
    except ValueError as exc:
        raise OpenAPIError("selection must be a number") from exc
    if selected < 1 or selected > len(labels):
        raise OpenAPIError("selection is out of range")
    return selected - 1


def choose_interactive(prompt: str, labels: list[str], default: int) -> int:
    import termios
    import tty

    selected = max(0, min(default - 1, len(labels) - 1))
    number = ""
    line_count = len(labels) + 1
    input_fd = sys.stdin.fileno()

    print(prompt)
    print("使用 ↑/↓ 移动，Enter 确认；也可输入编号后按 Enter；q 取消。")

    def render(first: bool = False) -> None:
        if not first:
            sys.stdout.write(f"\033[{line_count}A")
        for index, label in enumerate(labels):
            pointer = "▶" if index == selected else " "
            sys.stdout.write(
                f"\r\033[2K  {pointer} {index + 1}. {label}\n"
            )
        typed = f"编号：{number}" if number else "编号：（可直接按 Enter）"
        sys.stdout.write(f"\r\033[2K  {typed}\n")
        sys.stdout.flush()

    old_settings = termios.tcgetattr(input_fd)
    render(first=True)
    try:
        tty.setcbreak(input_fd)
        while True:
            char = os.read(input_fd, 1).decode("utf-8", "ignore")
            if char in {"\r", "\n"}:
                if number:
                    value = int(number)
                    if 1 <= value <= len(labels):
                        selected = value - 1
                        break
                    number = ""
                    render()
                    continue
                break
            if char == "\x1b":
                ready, _, _ = select.select([input_fd], [], [], 0.1)
                sequence = (
                    os.read(input_fd, 2).decode("utf-8", "ignore")
                    if ready
                    else ""
                )
                if sequence == "[A":
                    selected = (selected - 1) % len(labels)
                    number = ""
                    render()
                elif sequence == "[B":
                    selected = (selected + 1) % len(labels)
                    number = ""
                    render()
                continue
            if char in {"q", "Q", "\x03"}:
                raise OpenAPIError("用户取消配置")
            if char in {"\x7f", "\b"}:
                number = number[:-1]
                render()
                continue
            if char.isdigit():
                number += char
                render()
    finally:
        termios.tcsetattr(input_fd, termios.TCSADRAIN, old_settings)
    print(f"已选择：{selected + 1}. {labels[selected]}")
    return selected


def masked_user(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]


def display_local_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.home().resolve())
    except (OSError, ValueError):
        return path.name
    return "~/" + str(relative)


def redact_path(value: Any, home_path: str) -> Any:
    if isinstance(value, str) and home_path and value.startswith(home_path):
        return "$REMOTE_HOME" + value[len(home_path) :]
    return value


def setup_command(action: str, timeout: int) -> None:
    existing = load_metadata()
    if action == "auto":
        action = "modify" if existing else "new"
    if action == "status":
        credentials, provider = load_credentials()
        print("SCNet AI Chat OpenAPI configuration")
        print(f"metadata={display_local_path(metadata_path())}")
        print(f"credentials={provider or 'not configured'}")
        if existing:
            print(f"region={existing.get('region_name') or 'selected'}")
            print(f"scheduler={existing.get('scheduler_name') or 'selected'}")
            print(f"user={masked_user(str(existing.get('username') or ''))}")
            print(
                "home="
                + (
                    "$REMOTE_HOME"
                    if existing.get("home_path")
                    else "not discovered"
                )
            )
        else:
            print("region=not selected; run `scnet-aichat setup new`")
        if credentials and provider == "environment":
            print("note=credentials are supplied by environment variables")
        return
    if action == "reset":
        for path in (metadata_path(), backend_path()):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        print("Removed scnet-aichat OpenAPI metadata.")
        print("Shared scnet-hpc-openapi credentials were preserved.")
        return
    if action == "reset-credentials":
        deleted, provider = delete_credentials()
        print(
            f"{provider or 'secure store'} credentials="
            f"{'removed' if deleted else 'not present'}"
        )
        return
    if action == "new" and existing:
        raise OpenAPIError("OpenAPI is already configured; use `setup modify`")
    if action == "modify" and not existing:
        raise OpenAPIError("OpenAPI is not configured; use `setup new`")
    if not sys.stdin.isatty():
        raise OpenAPIError("setup requires an interactive terminal")

    credentials, provider = load_credentials()
    use_saved = bool(credentials) and ask_yes_no(
        f"是否使用 {provider} 中已有的 OpenAPI 凭据？", default=True
    )
    entered = not use_saved
    if not use_saved:
        user = ask("SCNet 平台用户名", str(existing.get("platform_user") or ""))
        access_key = getpass.getpass("AccessKey: ").strip()
        secret_key = getpass.getpass("SecretKey: ").strip()
        if not user or not access_key or not secret_key:
            raise OpenAPIError("username, AccessKey, and SecretKey are required")
        credentials = {
            "user": user,
            "access_key": access_key,
            "secret_key": secret_key,
        }
        os.environ["SCNET_OPENAPI_USER"] = user
        os.environ["SCNET_OPENAPI_ACCESS_KEY"] = access_key
        os.environ["SCNET_OPENAPI_SECRET_KEY"] = secret_key
    assert credentials is not None

    client = Client(timeout)
    contexts = client.discover_contexts()
    if not contexts:
        raise OpenAPIError("the account has no OpenAPI HPC/Slurm region")
    labels = [
        str(item.get("region_name") or f"区域 {index + 1}")
        for index, item in enumerate(contexts)
    ]
    current_region = str(existing.get("region_id") or DEFAULT_REGION_ID)
    default_region = next(
        (
            index + 1
            for index, item in enumerate(contexts)
            if item["region_id"] == current_region
        ),
        1,
    )
    selected = contexts[choose("选择默认 SCNet Region：", labels, default_region)]
    schedulers = selected["schedulers"]
    if len(schedulers) == 1:
        scheduler = schedulers[0]
    else:
        scheduler_labels = [
            str(item.get("name") or f"调度器 {index + 1}")
            for index, item in enumerate(schedulers)
        ]
        scheduler = schedulers[
            choose("选择默认 Scheduler：", scheduler_labels, 1)
        ]

    stored_provider = provider
    if entered:
        if secure_store_name():
            stored_provider = store_credentials(
                credentials["user"],
                credentials["access_key"],
                credentials["secret_key"],
            )
            print(f"Credentials stored in {stored_provider}.")
        else:
            stored_provider = "environment required"
            print(
                "No supported secure credential store is available. "
                "Credentials were not written to disk; export "
                "SCNET_OPENAPI_USER, SCNET_OPENAPI_ACCESS_KEY, and "
                "SCNET_OPENAPI_SECRET_KEY before use."
            )
    save_metadata(
        {
            "version": 1,
            "platform_user": credentials["user"],
            "credential_provider": stored_provider,
            "region_id": selected["region_id"],
            "region_name": selected.get("region_name"),
            "scheduler_id": scheduler["id"],
            "scheduler_name": scheduler.get("name"),
            "username": selected.get("username"),
            "home_path": selected.get("home_path"),
        }
    )
    print("OpenAPI configuration saved.")
    print(f"region={selected.get('region_name') or 'selected'}")
    print(f"scheduler={scheduler.get('name') or 'selected'}")
    print(f"user={masked_user(str(selected.get('username') or ''))}")
    print("home=$REMOTE_HOME")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=30)
    sub = parser.add_subparsers(dest="operation", required=True)

    setup = sub.add_parser("setup")
    setup.add_argument(
        "action",
        nargs="?",
        choices=(
            "auto",
            "new",
            "modify",
            "status",
            "reset",
            "reset-credentials",
        ),
        default="auto",
    )
    sub.add_parser("doctor")
    sub.add_parser("context")

    mkdir = sub.add_parser("mkdir")
    mkdir.add_argument("path")

    upload = sub.add_parser("upload")
    upload.add_argument("local_path")
    upload.add_argument("remote_directory")
    upload.add_argument("--cover", action="store_true")

    submit = sub.add_parser("submit")
    submit.add_argument("--name", required=True)
    submit.add_argument("--command", required=True)
    submit.add_argument("--work-dir", required=True)
    submit.add_argument("--queue", required=True)
    submit.add_argument("--cpus", type=int, required=True)
    submit.add_argument("--dcus", type=int, required=True)
    submit.add_argument("--memory", required=True)
    submit.add_argument("--walltime", required=True)
    submit.add_argument("--stdout", required=True)
    submit.add_argument("--stderr", required=True)

    job = sub.add_parser("job")
    job.add_argument("job_id")
    job.add_argument(
        "--field",
        choices=("state", "stdout", "stderr", "work_dir"),
    )

    cancel = sub.add_parser("cancel")
    cancel.add_argument("job_id")

    read = sub.add_parser("read")
    read.add_argument("path")

    install_worker = sub.add_parser("install-worker")
    install_worker.add_argument("--worker", required=True)
    install_worker.add_argument("--remote-app-dir", required=True)

    submit_chat = sub.add_parser("submit-chat")
    submit_chat.add_argument("--worker", required=True)
    submit_chat.add_argument("--request-dir", required=True)
    submit_chat.add_argument("--file", action="append", default=[])
    submit_chat.add_argument("--name", required=True)
    submit_chat.add_argument("--command", required=True)
    submit_chat.add_argument("--queue", required=True)
    submit_chat.add_argument("--cpus", type=int, required=True)
    submit_chat.add_argument("--dcus", type=int, required=True)
    submit_chat.add_argument("--memory", required=True)
    submit_chat.add_argument("--walltime", required=True)
    submit_chat.add_argument("--stdout", required=True)
    submit_chat.add_argument("--stderr", required=True)

    wait = sub.add_parser("wait")
    wait.add_argument("job_id")
    wait.add_argument("--poll-seconds", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.timeout < 1 or args.timeout > 600:
        raise OpenAPIError("timeout must be between 1 and 600 seconds")
    if args.operation == "setup":
        setup_command(args.action, args.timeout)
        return 0

    client = Client(args.timeout)
    context = client.context(None, None)
    if args.operation == "doctor":
        _, provider = load_credentials()
        print("backend=openapi")
        print(f"credentials={provider or 'not configured'}")
        print(f"region={context.get('region_name') or context['region_id']}")
        print(f"scheduler={context.get('scheduler_name') or context['scheduler_id']}")
        print(f"user={masked_user(context['username'])}")
        print("home=$REMOTE_HOME")
    elif args.operation == "context":
        print(
            "\t".join(
                (
                    context["home_path"],
                    context["username"],
                    context["region_id"],
                    context["scheduler_id"],
                )
            )
        )
    elif args.operation == "mkdir":
        client.mkdir(context, args.path)
    elif args.operation == "upload":
        client.upload(
            context,
            Path(args.local_path).expanduser(),
            args.remote_directory,
            cover=args.cover,
        )
    elif args.operation == "submit":
        if args.cpus < 1 or args.dcus < 0:
            raise OpenAPIError("cpus must be positive and dcus must be non-negative")
        print(client.submit(context, args))
    elif args.operation == "job":
        job = client.job(context, args.job_id)
        if args.field:
            print(job.get(args.field) or "")
        else:
            safe = {
                key: redact_path(value, context["home_path"])
                for key, value in job.items()
            }
            print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.operation == "cancel":
        client.cancel(context, args.job_id)
        print(f"Cancellation requested for job {args.job_id}")
    elif args.operation == "read":
        sys.stdout.buffer.write(client.read_file(context, args.path))
    elif args.operation == "install-worker":
        app_dir = args.remote_app_dir
        client.mkdir(context, posixpath.join(app_dir, "requests"))
        client.upload(
            context,
            Path(args.worker).expanduser(),
            app_dir,
            cover=True,
        )
    elif args.operation == "submit-chat":
        if args.cpus < 1 or args.dcus < 0:
            raise OpenAPIError("cpus must be positive and dcus must be non-negative")
        request_dir = args.request_dir
        app_dir = posixpath.dirname(posixpath.dirname(request_dir.rstrip("/")))
        client.mkdir(context, request_dir)
        client.upload(
            context,
            Path(args.worker).expanduser(),
            app_dir,
            cover=True,
        )
        for path in args.file:
            client.upload(
                context,
                Path(path).expanduser(),
                request_dir,
                cover=True,
            )
        args.work_dir = request_dir
        print(client.submit(context, args))
    elif args.operation == "wait":
        if args.poll_seconds < 1 or args.poll_seconds > 300:
            raise OpenAPIError("poll-seconds must be between 1 and 300")
        last = ""
        failed = {
            "FAILED",
            "CANCELLED",
            "TIMEOUT",
            "OUT_OF_MEMORY",
            "NODE_FAIL",
            "PREEMPTED",
        }
        while True:
            state = str(client.job(context, args.job_id).get("state") or "")
            if state != last:
                print(
                    f"job={args.job_id} state={state or 'WAITING_FOR_ACCOUNTING'}",
                    file=sys.stderr,
                    flush=True,
                )
                last = state
            if state == "COMPLETED":
                return 0
            if state in failed:
                return 1
            time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OpenAPIError, KeyboardInterrupt) as exc:
        message = "cancelled" if isinstance(exc, KeyboardInterrupt) else str(exc)
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)
