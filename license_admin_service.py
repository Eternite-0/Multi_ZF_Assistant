import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from scripts.license_admin import (
    append_license_record,
    create_license_record,
)


DEFAULT_REPO_URL = "git@gitee.com:ConfusePack/HWID_2.git"
DEFAULT_BRANCH = "master"
DEFAULT_PRIVATE_KEY = "license_private.pem"
DEFAULT_LICENSES = "licenses.json"
DEFAULT_SSH_KEY = str(Path.home() / ".ssh" / "gitee_ebpf_ed25519")


@dataclass
class LicenseIssueInput:
    hwid: str
    owner: str = ""
    note: str = ""
    expires_at: str = "permanent"
    features: str = "full"
    private_key_path: str = DEFAULT_PRIVATE_KEY
    licenses_path: str = DEFAULT_LICENSES


@dataclass
class PublishInput:
    issue: LicenseIssueInput
    repo_url: str = DEFAULT_REPO_URL
    branch: str = DEFAULT_BRANCH
    ssh_key_path: str = DEFAULT_SSH_KEY


def _feature_list(features: str) -> List[str]:
    return [item.strip() for item in str(features).split(",") if item.strip()] or ["full"]


def load_and_validate_private_key(private_key_path: str) -> str:
    path = Path(private_key_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到私钥: {private_key_path}")

    private_key_pem = path.read_text(encoding="utf-8")
    if "BEGIN RSA PUBLIC KEY" in private_key_pem or "BEGIN PUBLIC KEY" in private_key_pem:
        raise ValueError("你选的是公钥 license_public.pem，请选择私钥 license_private.pem。")
    if "BEGIN RSA PRIVATE KEY" not in private_key_pem:
        raise ValueError("私钥文件格式不正确，请选择 license_private.pem。")
    return private_key_pem


def issue_license_to_file(
    issue: LicenseIssueInput,
    today: Optional[date] = None,
) -> Dict:
    private_key_pem = load_and_validate_private_key(issue.private_key_path)
    record = create_license_record(
        hwid=issue.hwid,
        private_key_pem=private_key_pem,
        expires_at=issue.expires_at or "permanent",
        features=_feature_list(issue.features),
        owner=issue.owner.strip() or None,
        note=issue.note.strip() or None,
        issued_at=(today or date.today()).isoformat(),
    )
    append_license_record(issue.licenses_path, record)
    return record


def build_git_ssh_command(ssh_key_path: str) -> str:
    key_path = str(Path(ssh_key_path))
    return (
        f'ssh -i "{key_path}" '
        "-o IdentitiesOnly=yes "
        "-o StrictHostKeyChecking=accept-new "
        "-o BatchMode=yes"
    )


def _run_git(
    args: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    runner: Callable = subprocess.run,
) -> subprocess.CompletedProcess:
    result = runner(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        output = "\n".join(
            item for item in [result.stdout, result.stderr] if item
        ).strip()
        raise RuntimeError(output or f"命令失败: {' '.join(args)}")
    return result


def publish_license_to_gitee(
    publish: PublishInput,
    runner: Callable = subprocess.run,
) -> Tuple[Dict, str]:
    if not Path(publish.issue.private_key_path).exists():
        raise FileNotFoundError(f"找不到私钥: {publish.issue.private_key_path}")
    if not Path(publish.ssh_key_path).exists():
        raise FileNotFoundError(f"找不到 SSH 私钥: {publish.ssh_key_path}")

    temp_root = tempfile.mkdtemp(prefix="hwid-license-gitee-")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_SSH_COMMAND"] = build_git_ssh_command(publish.ssh_key_path)

    try:
        _run_git(["git", "clone", publish.repo_url, temp_root], env=env, runner=runner)
        _run_git(["git", "checkout", "-B", publish.branch], cwd=temp_root, env=env, runner=runner)

        remote_license = Path(temp_root) / "licenses.json"
        local_license = Path(publish.issue.licenses_path)
        if not remote_license.exists() and local_license.exists():
            shutil.copy2(local_license, remote_license)

        temp_issue = LicenseIssueInput(
            hwid=publish.issue.hwid,
            owner=publish.issue.owner,
            note=publish.issue.note,
            expires_at=publish.issue.expires_at,
            features=publish.issue.features,
            private_key_path=publish.issue.private_key_path,
            licenses_path=str(remote_license),
        )
        record = issue_license_to_file(temp_issue)

        local_license.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(remote_license, local_license)

        _run_git(["git", "add", "licenses.json"], cwd=temp_root, env=env, runner=runner)
        commit_message = f"Update license for {record['hwid_hash'][:12]}"
        commit = runner(
            ["git", "-c", "user.name=License Admin", "-c", "user.email=license-admin@example.local",
             "commit", "-m", commit_message],
            cwd=temp_root,
            env=env,
            text=True,
            capture_output=True,
        )
        commit_output = "\n".join(item for item in [commit.stdout, commit.stderr] if item).strip()
        if commit.returncode != 0 and "nothing to commit" not in commit_output:
            raise RuntimeError(commit_output or "git commit 失败")

        _run_git(["git", "push", "origin", publish.branch], cwd=temp_root, env=env, runner=runner)
        return record, commit_output
    finally:
        resolved = Path(temp_root).resolve()
        temp_base = Path(tempfile.gettempdir()).resolve()
        if str(resolved).lower().startswith(str(temp_base).lower()):
            shutil.rmtree(resolved, ignore_errors=True)
