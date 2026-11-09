#!/usr/bin/env python3
"""Collect bounded source-quality command outputs for a clean candidate checkout."""

import argparse
import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

import validate_promotion_evidence as evidence

SOURCE_COMMANDS = evidence.SOURCE_COMMANDS
MAX_OUTPUT = 1024 * 1024
TIMEOUT_SECONDS = 1800


def run_bounded(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    outputs = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("source command timed out")
            for key, _ in selector.select(min(remaining, 1)):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    outputs[key.data].extend(chunk)
                    if len(outputs[key.data]) > MAX_OUTPUT:
                        raise ValueError("source command output exceeds bound")
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        return subprocess.CompletedProcess(command, code, outputs["stdout"].decode("utf-8"), outputs["stderr"].decode("utf-8"))
    except (ValueError, UnicodeError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise ValueError("source command could not be collected safely")
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()


def collect(workspace: Path, output: Path, tag: str, commit: str, image: str, runner=run_bounded) -> dict[str, str]:
    if (evidence.candidate_archive.release.SEMVER_TAG.fullmatch(tag) is None
        or evidence.COMMIT.fullmatch(commit) is None or evidence.IMAGE.fullmatch(image) is None
        or not image.startswith(f"ghcr.io/sponzey-lab/sponzey-edge:{tag}@sha256:")
        or output.exists() or output.is_symlink() or not output.parent.is_dir()):
        raise ValueError("collector input is invalid")

    def check_source() -> None:
        status = runner(["git", "status", "--porcelain=v1", "--untracked-files=normal"], workspace)
        revision = runner(["git", "rev-parse", "HEAD"], workspace)
        if status.returncode != 0 or status.stdout.strip() or revision.returncode != 0 or revision.stdout.strip() != commit:
            raise ValueError("source must be clean and match candidate commit")

    check_source()
    candidate = {"tag": tag, "commit": commit, "image": image}
    results = {}
    for name, command in SOURCE_COMMANDS.items():
        result = runner(command, workspace)
        original = {"command": command, "source_commit": commit, "exit_code": result.returncode,
                    "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode != 0:
            raise ValueError("source quality command failed")
        try:
            evidence.decode_json(json.dumps(original).encode())
        except evidence.PromotionError:
            raise ValueError("source output cannot be published safely")
        results[name] = original
    check_source()

    created: list[Path] = []
    output.mkdir(mode=0o700)
    try:
        def write(name: str, value: object) -> dict[str, str]:
            raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            path = output / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                created.append(path)
                stream.write(raw)
            return {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}

        observations = {name: {"value": 0, "output": write(f"source-{name}.json", value)}
                        for name, value in results.items()}
        trace = write("source-trace.json", {"schema_version": 1, "kind": "source_quality", "candidate": candidate, "observations": observations})
        return write("source-quality.json", {"schema_version": 1, "kind": "source_quality", "candidate": candidate,
                                            "checks": {name: 0 for name in SOURCE_COMMANDS}, "trace": trace})
    except (OSError, ValueError):
        for path in reversed(created):
            path.unlink(missing_ok=True)
        output.rmdir()
        raise ValueError("source evidence could not be published")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    try:
        result = collect(args.workspace, args.output, args.tag, args.commit, args.image)
    except (OSError, ValueError):
        print("SOURCE_EVIDENCE_INVALID", file=sys.stderr)
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
