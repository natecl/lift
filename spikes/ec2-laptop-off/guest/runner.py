#!/usr/bin/env python3
"""Provider-blind process supervisor for the disposable Lift EC2 spike.

The runner accepts a reviewed recipe containing an executable and an argument
array. It never evaluates a shell string and it contains no Codex-specific
branches. Root owns lifecycle control; the workload itself runs as `lift`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


UNIT_NAME = "lift-workload.service"
UNIT_PATH = Path("/etc/systemd/system") / UNIT_NAME
STATE_PATH = Path("/var/lib/lift-spike/runner-state.json")
HEALTH_PATH = Path("/run/lift-spike-runner/health.json")
WORKSPACE_ROOT = Path("/home/lift/workspaces")
RECIPE_ROOT = Path("/opt/lift-spike/recipes")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
UNIT_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9._/-]+$")
# Phase 0 root-owned permission policy. This is reviewed recipe data, not a
# provider lifecycle branch. Supporting another recipe requires explicitly
# extending this allowlist during installation; arbitrary home state is denied.
APPROVED_PERSISTENT_PATHS = frozenset(
    {
        "/home/lift/.codex",
        "/home/lift/.cache/codex",
    }
)
MAX_CAPTURED_OUTPUT_BYTES = 64 * 1024


class RunnerError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RunnerError(f"{path} must contain a JSON object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    parent = path.parent
    if parent.is_symlink():
        raise RunnerError(f"atomic JSON parent cannot be a symbolic link: {parent}")
    try:
        parent.mkdir(parents=True, exist_ok=True)
        parent_stat = os.lstat(parent)
    except OSError as exc:
        raise RunnerError(f"cannot prepare atomic JSON parent {parent}: {exc}") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise RunnerError(f"atomic JSON parent must be a real directory: {parent}")

    parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    parent_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = -1
    temporary_descriptor = -1
    temporary_name: str | None = None
    try:
        parent_descriptor = os.open(parent, parent_flags)

        def reject_unsafe_target() -> None:
            try:
                target_stat = os.stat(
                    path.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return
            if stat.S_ISLNK(target_stat.st_mode):
                raise RunnerError(f"atomic JSON target cannot be a symbolic link: {path}")
            if not stat.S_ISREG(target_stat.st_mode):
                raise RunnerError(f"atomic JSON target must be a regular file: {path}")

        reject_unsafe_target()
        temporary_descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary_name = Path(temporary_path).name
        descriptor_stat = os.fstat(temporary_descriptor)
        linked_stat = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(linked_stat.st_mode)
            or descriptor_stat.st_dev != linked_stat.st_dev
            or descriptor_stat.st_ino != linked_stat.st_ino
        ):
            raise RunnerError("atomic JSON temporary file escaped its parent directory")

        os.fchmod(temporary_descriptor, 0o600)
        handle = os.fdopen(temporary_descriptor, "w", encoding="utf-8")
        temporary_descriptor = -1
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        reject_unsafe_target()
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    except RunnerError:
        raise
    except OSError as exc:
        raise RunnerError(f"cannot atomically write JSON to {path}: {exc}") from exc
    finally:
        if temporary_descriptor >= 0:
            try:
                os.close(temporary_descriptor)
            except OSError:
                pass
        if temporary_name is not None and parent_descriptor >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except OSError:
                pass
        if parent_descriptor >= 0:
            try:
                os.close(parent_descriptor)
            except OSError:
                pass


def recipe_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained_path(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validated_persistent_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if raw_path not in APPROVED_PERSISTENT_PATHS:
        raise RunnerError("recipe requested a persistent path outside the reviewed policy")
    if not candidate.is_absolute() or candidate.is_symlink():
        raise RunnerError("persistent paths must be absolute, real directories")
    resolved = candidate.resolve(strict=True)
    if resolved != candidate or not resolved.is_dir():
        raise RunnerError("persistent paths must resolve exactly to real directories")
    return resolved


def validated_process(recipe: dict[str, Any], name: str, *, required: bool) -> None:
    process = recipe.get(name)
    if process is None and not required:
        return
    if not isinstance(process, dict):
        raise RunnerError(f"{name} must be an object")
    executable = process.get("executable")
    arguments = process.get("arguments")
    if not isinstance(executable, str) or not executable.startswith("/"):
        raise RunnerError(f"{name}.executable must be an absolute path")
    executable_path = Path(executable)
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise RunnerError(f"{name} executable is not executable: {executable}")
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        raise RunnerError(f"{name}.arguments must be an array of strings")
    timeout = process.get("timeoutSeconds", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 300:
        raise RunnerError(f"{name}.timeoutSeconds must be an integer from 1 to 300")
    assertions = process.get("jsonEquals")
    if assertions is not None:
        if not isinstance(assertions, dict) or not assertions:
            raise RunnerError(f"{name}.jsonEquals must be a nonempty object")
        for pointer in assertions:
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise RunnerError(
                    f"{name}.jsonEquals keys must be absolute JSON Pointers"
                )
            for token in pointer.split("/")[1:]:
                if "~" in token.replace("~0", "").replace("~1", ""):
                    raise RunnerError(f"{name}.jsonEquals contains an invalid JSON Pointer")
    nonempty = process.get("jsonNonEmpty")
    if nonempty is not None:
        if (
            not isinstance(nonempty, list)
            or not nonempty
            or not all(isinstance(pointer, str) for pointer in nonempty)
            or len(set(nonempty)) != len(nonempty)
        ):
            raise RunnerError(f"{name}.jsonNonEmpty must be a nonempty unique string array")
        for pointer in nonempty:
            if not pointer.startswith("/"):
                raise RunnerError(
                    f"{name}.jsonNonEmpty entries must be absolute JSON Pointers"
                )
            for token in pointer.split("/")[1:]:
                if "~" in token.replace("~0", "").replace("~1", ""):
                    raise RunnerError(f"{name}.jsonNonEmpty contains an invalid JSON Pointer")


def validated_recipe(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    recipe_root = RECIPE_ROOT.resolve(strict=True)
    if not contained_path(resolved, recipe_root):
        raise RunnerError(f"recipe must be below {recipe_root}")

    recipe = read_json(resolved)
    required = {"schemaVersion", "id", "run", "persistentPaths", "networkPolicy", "restartPolicy"}
    missing = sorted(required.difference(recipe))
    if missing:
        raise RunnerError(f"recipe is missing required keys: {', '.join(missing)}")
    if recipe["schemaVersion"] != 1:
        raise RunnerError("unsupported recipe schemaVersion")
    if not isinstance(recipe["id"], str) or not ID_PATTERN.fullmatch(recipe["id"]):
        raise RunnerError("recipe id is invalid")

    process_mode = recipe.get("processMode", "foreground")
    if process_mode not in {"foreground", "detached"}:
        raise RunnerError("processMode must be foreground or detached")
    validated_process(recipe, "run", required=True)
    validated_process(recipe, "prepare", required=False)
    validated_process(recipe, "health", required=process_mode == "detached")
    validated_process(recipe, "readiness", required=False)
    validated_process(recipe, "stop", required=process_mode == "detached")
    if process_mode == "detached":
        health = recipe["health"]
        interval = health.get("intervalSeconds", 30)
        threshold = health.get("failureThreshold", 3)
        if isinstance(interval, bool) or not isinstance(interval, int) or not 5 <= interval <= 300:
            raise RunnerError("health.intervalSeconds must be an integer from 5 to 300")
        if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 10:
            raise RunnerError("health.failureThreshold must be an integer from 1 to 10")

    persistent_paths = recipe["persistentPaths"]
    if not isinstance(persistent_paths, list) or not all(
        isinstance(item, str) and item.startswith("/") for item in persistent_paths
    ):
        raise RunnerError("persistentPaths must be an array of absolute paths")
    if len(set(persistent_paths)) != len(persistent_paths):
        raise RunnerError("persistentPaths cannot contain duplicates")
    for persistent_path in persistent_paths:
        validated_persistent_path(persistent_path)

    network = recipe["networkPolicy"]
    if network != {"outbound": "internet", "metadataAccess": False}:
        raise RunnerError("the Phase 0 runner requires the reviewed network policy")
    if recipe["restartPolicy"] not in {"no", "never", "on-failure", "always"}:
        raise RunnerError("restartPolicy must be never, on-failure, or always")
    return recipe


def validated_workspace(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise RunnerError("workspace path must be absolute")
    if candidate.is_symlink():
        raise RunnerError("workspace path cannot be a symbolic link")
    resolved = candidate.resolve(strict=True)
    root = WORKSPACE_ROOT.resolve(strict=True)
    if resolved == root or not contained_path(resolved, root):
        raise RunnerError(f"workspace must be a child of {root}")
    if not resolved.is_dir():
        raise RunnerError("workspace is not a directory")
    current = resolved
    while current != root:
        if current.is_symlink():
            raise RunnerError(f"workspace parent cannot be a symbolic link: {current}")
        current = current.parent
    return resolved


def systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *arguments],
        check=check,
        text=True,
        capture_output=True,
    )


def systemd_path(value: str) -> str:
    if not UNIT_PATH_PATTERN.fullmatch(value):
        raise RunnerError("systemd unit paths contain unsupported characters")
    return value


def unit_text(recipe_path: Path, workspace: Path, recipe: dict[str, Any]) -> str:
    restart = "no" if recipe["restartPolicy"] in {"no", "never"} else recipe["restartPolicy"]
    stop_timeout = 30
    if recipe.get("processMode", "foreground") == "detached":
        stop_timeout = (
            recipe["health"].get("timeoutSeconds", 120)
            + recipe["stop"].get("timeoutSeconds", 120)
            + 5
        )
    writable_paths = [str(workspace), *recipe["persistentPaths"]]
    encoded_paths = " ".join(systemd_path(item) for item in writable_paths)
    encoded_recipe = systemd_path(str(recipe_path))
    encoded_workspace = systemd_path(str(workspace))
    return "\n".join(
        [
            "[Unit]",
            "Description=Lift provider-blind remote workload",
            "After=network-online.target",
            "Wants=network-online.target",
            f"RequiresMountsFor={encoded_paths}",
            "",
            "[Service]",
            "Type=simple",
            "User=lift",
            "Group=lift",
            "Environment=HOME=/home/lift",
            "Environment=PATH=/home/lift/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            f"WorkingDirectory={encoded_workspace}",
            "ExecStart=/usr/bin/python3 /opt/lift-spike/runner.py serve "
            f"--recipe {encoded_recipe} --workspace {encoded_workspace}",
            f"Restart={restart}",
            "RestartSec=3s",
            f"TimeoutStopSec={stop_timeout}s",
            "KillMode=mixed",
            "RuntimeDirectory=lift-spike-runner",
            "RuntimeDirectoryMode=0700",
            "UMask=0077",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            f"ReadWritePaths={encoded_paths}",
            "IPAddressDeny=169.254.169.254/32",
            "IPAddressDeny=fd00:ec2::254/128",
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "ProtectControlGroups=true",
            "RestrictSUIDSGID=true",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def process_environment(workspace: Path) -> dict[str, str]:
    return {
        "HOME": "/home/lift",
        "PATH": "/home/lift/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LIFT_WORKSPACE": str(workspace),
    }


def json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for encoded_token in pointer.split("/")[1:]:
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list) and token.isdigit():
            index = int(token)
            if index < len(current):
                current = current[index]
                continue
        raise RunnerError(f"JSON assertion path was missing: {pointer}")
    return current


def assert_process_output(process: dict[str, Any], name: str, output: bytes) -> None:
    assertions = process.get("jsonEquals")
    nonempty = process.get("jsonNonEmpty")
    if assertions is None and nonempty is None:
        return
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        raise RunnerError(f"{name} command returned no JSON output")
    try:
        value = json.loads(lines[-1])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerError(f"{name} command returned invalid JSON") from exc
    for pointer, expected in (assertions or {}).items():
        observed = json_pointer(value, pointer)
        if type(observed) is not type(expected) or observed != expected:
            raise RunnerError(f"{name} JSON assertion failed at {pointer}")
    for pointer in nonempty or []:
        observed = json_pointer(value, pointer)
        if not isinstance(observed, (str, list, dict)) or len(observed) == 0:
            raise RunnerError(f"{name} JSON nonempty assertion failed at {pointer}")


def invoke_with_capped_output(
    command: list[str], workspace: Path, timeout: int
) -> tuple[int, bytes]:
    try:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=process_environment(workspace),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RunnerError(f"cannot execute process: {exc}") from exc
    if process.stdout is None:
        process.kill()
        process.wait()
        raise RunnerError("cannot capture process output")

    captured = bytearray()
    output_exceeded = threading.Event()

    def drain() -> None:
        while True:
            chunk = process.stdout.read(8192)
            if not chunk:
                return
            remaining = MAX_CAPTURED_OUTPUT_BYTES + 1 - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > max(remaining, 0) or len(captured) > MAX_CAPTURED_OUTPUT_BYTES:
                output_exceeded.set()

    reader = threading.Thread(target=drain, name="lift-runner-output", daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.wait()
        raise RunnerError("process timed out") from exc
    finally:
        reader.join(timeout=2)
        if reader.is_alive():
            process.stdout.close()
            reader.join(timeout=1)
        else:
            process.stdout.close()
    if output_exceeded.is_set() or len(captured) > MAX_CAPTURED_OUTPUT_BYTES:
        raise RunnerError("process output exceeded the capture limit")
    return returncode, bytes(captured)


def invoke_process(recipe: dict[str, Any], name: str, workspace: Path) -> None:
    process = recipe[name]
    executable = process["executable"]
    command = [executable, *process["arguments"]]
    timeout = process.get("timeoutSeconds", 120)
    if process.get("jsonEquals") is not None or process.get("jsonNonEmpty") is not None:
        try:
            returncode, output = invoke_with_capped_output(command, workspace, timeout)
        except RunnerError as exc:
            raise RunnerError(f"{name} command failed: {exc}") from exc
        if returncode != 0:
            raise RunnerError(f"{name} command exited with status {returncode}")
        assert_process_output(process, name, output)
        return
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            check=False,
            env=process_environment(workspace),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(f"{name} command timed out") from exc
    except OSError as exc:
        raise RunnerError(f"cannot execute {name} command: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError(f"{name} command exited with status {completed.returncode}")


def write_health(
    *,
    recipe_path: Path,
    recipe: dict[str, Any],
    workspace: Path,
    healthy: bool,
    ready: bool,
    consecutive_failures: int,
    error: str | None = None,
    readiness_error: str | None = None,
) -> None:
    value: dict[str, Any] = {
        "checkedAtEpochSeconds": time.time(),
        "consecutiveFailures": consecutive_failures,
        "healthy": healthy,
        "ready": ready,
        "processMode": recipe.get("processMode", "foreground"),
        "recipeId": recipe["id"],
        "recipeSha256": recipe_hash(recipe_path),
        "supervisorPid": os.getpid(),
        "workspace": str(workspace),
    }
    if error is not None:
        value["error"] = error
    if readiness_error is not None:
        value["readinessError"] = readiness_error
    atomic_json(HEALTH_PATH, value)


def supervise_detached(
    recipe_path: Path,
    recipe: dict[str, Any],
    workspace: Path,
    stop_event: threading.Event,
) -> None:
    health = recipe["health"]
    interval = health.get("intervalSeconds", 30)
    failure_threshold = health.get("failureThreshold", 3)
    consecutive_failures = 0
    try:
        invoke_process(recipe, "run", workspace)
        if "prepare" in recipe:
            invoke_process(recipe, "prepare", workspace)
        while not stop_event.is_set():
            try:
                invoke_process(recipe, "health", workspace)
            except RunnerError as exc:
                consecutive_failures += 1
                write_health(
                    recipe_path=recipe_path,
                    recipe=recipe,
                    workspace=workspace,
                    healthy=False,
                    ready=False,
                    consecutive_failures=consecutive_failures,
                    error=str(exc),
                )
                if consecutive_failures >= failure_threshold:
                    raise RunnerError(
                        f"health command failed {consecutive_failures} consecutive times"
                    ) from exc
            else:
                consecutive_failures = 0
                ready = True
                readiness_error = None
                if "readiness" in recipe:
                    try:
                        invoke_process(recipe, "readiness", workspace)
                    except RunnerError as exc:
                        ready = False
                        readiness_error = str(exc)
                write_health(
                    recipe_path=recipe_path,
                    recipe=recipe,
                    workspace=workspace,
                    healthy=True,
                    ready=ready,
                    consecutive_failures=0,
                    readiness_error=readiness_error,
                )
            stop_event.wait(interval)
    finally:
        active_exception = sys.exc_info()[1]
        try:
            invoke_process(recipe, "stop", workspace)
        except RunnerError:
            if active_exception is None:
                raise


def unit_main_pid() -> int:
    completed = systemctl(
        "show", UNIT_NAME, "--property=MainPID", "--value", check=False
    )
    try:
        value = int(completed.stdout.strip())
    except ValueError:
        return 0
    return value if completed.returncode == 0 and value > 0 else 0


def health_snapshot(
    requested: dict[str, Any], active: bool, main_pid: int
) -> dict[str, Any]:
    if requested.get("processMode") != "detached":
        return {"fresh": active, "healthy": active, "source": "systemd"}
    if not HEALTH_PATH.exists():
        return {"fresh": False, "healthy": False, "source": "detached-monitor"}
    try:
        health = read_json(HEALTH_PATH)
    except RunnerError as exc:
        return {
            "error": str(exc),
            "fresh": False,
            "healthy": False,
            "source": "detached-monitor",
        }
    checked_at = health.get("checkedAtEpochSeconds")
    interval = requested.get("healthIntervalSeconds", 30)
    timeout = requested.get("healthTimeoutSeconds", 120)
    fresh_for = interval + timeout + 5
    fresh = (
        isinstance(checked_at, (int, float))
        and not isinstance(checked_at, bool)
        and 0 <= time.time() - checked_at <= fresh_for
    )
    identity_matches = (
        health.get("recipeSha256") == requested.get("recipeSha256")
        and health.get("workspace") == requested.get("workspace")
    )
    supervisor_matches = main_pid > 0 and health.get("supervisorPid") == main_pid
    healthy = (
        active
        and fresh
        and identity_matches
        and supervisor_matches
        and health.get("healthy") is True
    )
    readiness_configured = requested.get("readinessConfigured") is True
    ready = healthy and (
        health.get("ready") is True
        if readiness_configured
        else health.get("healthy") is True
    )
    return {
        **health,
        "fresh": fresh,
        "healthy": healthy,
        "identityMatches": identity_matches,
        "ready": ready,
        "readinessConfigured": readiness_configured,
        "source": "detached-monitor",
        "supervisorMatches": supervisor_matches,
    }


def wait_for_detached_health(requested: dict[str, Any]) -> dict[str, Any]:
    deadline = time.monotonic() + requested.get("startTimeoutSeconds", 120)
    latest: dict[str, Any] = {
        "fresh": False,
        "healthy": False,
        "source": "detached-monitor",
    }
    while time.monotonic() < deadline:
        active = systemctl("is-active", UNIT_NAME, check=False).returncode == 0
        latest = health_snapshot(requested, active, unit_main_pid())
        if latest.get("healthy") is True:
            return latest
        time.sleep(1)
    raise RunnerError(f"detached workload did not become healthy: {latest}")


def cmd_start(args: argparse.Namespace) -> None:
    if os.geteuid() != 0:
        raise RunnerError("start must run as root")
    recipe_path = Path(args.recipe).resolve(strict=True)
    recipe = validated_recipe(recipe_path)
    workspace = validated_workspace(args.workspace)
    requested = {
        "processMode": recipe.get("processMode", "foreground"),
        "readinessConfigured": "readiness" in recipe,
        "recipeId": recipe["id"],
        "recipePath": str(recipe_path),
        "recipeSha256": recipe_hash(recipe_path),
        "workspace": str(workspace),
    }
    if requested["processMode"] == "detached":
        requested.update(
            {
                "healthIntervalSeconds": recipe["health"].get("intervalSeconds", 30),
                "healthTimeoutSeconds": recipe["health"].get("timeoutSeconds", 120),
                "startTimeoutSeconds": recipe["run"].get("timeoutSeconds", 120)
                + recipe.get("prepare", {}).get("timeoutSeconds", 0)
                + recipe["health"].get("timeoutSeconds", 120)
                + 15,
            }
        )

    if STATE_PATH.exists():
        existing = read_json(STATE_PATH)
        active = systemctl("is-active", UNIT_NAME, check=False).returncode == 0
        if active and all(existing.get(key) == value for key, value in requested.items()):
            health = (
                wait_for_detached_health(requested)
                if requested["processMode"] == "detached"
                else health_snapshot(requested, active, unit_main_pid())
            )
            print(
                json.dumps(
                    {**requested, "state": "active", "changed": False, "health": health},
                    sort_keys=True,
                )
            )
            return
        if active:
            raise RunnerError("a different workload is already active")

    if HEALTH_PATH.exists():
        HEALTH_PATH.unlink()
    UNIT_PATH.write_text(unit_text(recipe_path, workspace, recipe), encoding="utf-8")
    os.chmod(UNIT_PATH, 0o644)
    atomic_json(STATE_PATH, requested)
    systemctl("daemon-reload")
    systemctl("enable", "--now", UNIT_NAME)
    active = systemctl("is-active", UNIT_NAME, check=False).returncode == 0
    if not active:
        raise RunnerError("systemd did not keep the workload active")
    health = (
        wait_for_detached_health(requested)
        if requested["processMode"] == "detached"
        else health_snapshot(requested, active, unit_main_pid())
    )
    print(
        json.dumps(
            {**requested, "state": "active", "changed": True, "health": health},
            sort_keys=True,
        )
    )


def cmd_stop(_: argparse.Namespace) -> None:
    if os.geteuid() != 0:
        raise RunnerError("stop must run as root")
    changed = systemctl("is-active", UNIT_NAME, check=False).returncode == 0
    stopped = systemctl("disable", "--now", UNIT_NAME, check=False)
    if stopped.returncode != 0:
        raise RunnerError("systemd could not disable and stop the workload")
    if systemctl("is-active", UNIT_NAME, check=False).returncode == 0:
        raise RunnerError("the workload remained active after stop")
    if HEALTH_PATH.exists():
        HEALTH_PATH.unlink()
    print(json.dumps({"state": "inactive", "changed": changed}, sort_keys=True))


def cmd_status(_: argparse.Namespace) -> int:
    active = systemctl("is-active", UNIT_NAME, check=False).returncode == 0
    properties = systemctl(
        "show",
        UNIT_NAME,
        "--property=ActiveState,SubState,MainPID,ExecMainStatus",
        check=False,
    ).stdout.strip()
    state = read_json(STATE_PATH) if STATE_PATH.exists() else {}
    health = health_snapshot(state, active, unit_main_pid())
    state.update(
        {
            "active": active,
            "healthy": health.get("healthy") is True,
            "ready": health.get("ready") is True,
            "health": health,
            "systemd": properties,
        }
    )
    print(json.dumps(state, sort_keys=True))
    return 0


def cmd_serve(args: argparse.Namespace) -> None:
    if os.geteuid() == 0:
        raise RunnerError("serve refuses to run as root")
    recipe_path = Path(args.recipe).resolve(strict=True)
    recipe = validated_recipe(recipe_path)
    workspace = validated_workspace(args.workspace)
    os.chdir(workspace)
    if recipe.get("processMode", "foreground") == "detached":
        stop_event = threading.Event()

        def request_stop(_: int, __: Any) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        supervise_detached(recipe_path, recipe, workspace, stop_event)
        return
    run = recipe["run"]
    executable = run["executable"]
    os.execve(
        executable,
        [executable, *run["arguments"]],
        process_environment(workspace),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("start", cmd_start), ("serve", cmd_serve)):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--recipe", required=True)
        subparser.add_argument("--workspace", required=True)
        subparser.set_defaults(handler=handler)
    stop = subparsers.add_parser("stop")
    stop.set_defaults(handler=cmd_stop)
    status = subparsers.add_parser("status")
    status.set_defaults(handler=cmd_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
        return result if isinstance(result, int) else 0
    except RunnerError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
