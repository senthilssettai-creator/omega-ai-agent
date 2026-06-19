"""OMEGA Security System - Permission model and approval gates"""

import asyncio
import hashlib
import json
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import structlog

from omega.config import config

logger = structlog.get_logger(__name__)


class PermissionLevel(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


import re

# Patterns are either:
#  - plain strings matched as whole-word/phrase substrings (safe for multi-word phrases
#    like "rm -rf /" since they contain non-alphanumeric chars and won't false-positive)
#  - single bare words, which we match with \b...\b word boundaries to avoid matching
#    inside unrelated identifiers (e.g. "format" should not match "format_string.py")
RISK_PATTERNS = {
    RiskLevel.CRITICAL: [
        "rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:",
        "sudo rm", "drop database", "truncate table",
        "git push --force", "> /dev/sda", "git push -f",
    ],
    RiskLevel.HIGH: [
        "rm -rf", "delete from", "drop table",
        "kubectl delete", "terraform destroy", "npm publish",
        "pip install --upgrade", "chmod -r 777", "git push",
    ],
    RiskLevel.MEDIUM: [
        "git commit", "docker rm", "pip install", "npm install", "git merge",
    ],
}

# Bare single words that need word-boundary matching to avoid matching substrings
# inside unrelated filenames/identifiers (e.g. "format" inside "format_helper.py")
RISK_WORD_PATTERNS = {
    RiskLevel.CRITICAL: ["format"],
    RiskLevel.HIGH: [],
    RiskLevel.MEDIUM: ["rm", "mv", "cp"],
}


def _matches_phrase(action_lower: str, pattern: str) -> bool:
    """Match a multi-char phrase pattern as a substring (safe since these phrases
    contain spaces/special chars unlikely to appear inside unrelated tokens)."""
    return pattern in action_lower


def _matches_word(action_lower: str, word: str) -> bool:
    """Match a bare word using word boundaries to avoid false positives like
    'format' matching inside 'format_string_helper.py'."""
    return re.search(rf"\b{re.escape(word)}\b", action_lower) is not None


class SecurityManager:
    """Manages permissions and approval workflows"""

    def __init__(self, approval_callback: Optional[Callable] = None):
        self._permissions: Dict[str, PermissionLevel] = {}
        self._approval_callback = approval_callback
        self._pending_approvals: Dict[str, Dict] = {}
        self._approved_hashes: Set[str] = set()

    def assess_risk(self, action: str) -> RiskLevel:
        """Assess the risk level of an action"""
        action_lower = action.lower()
        for level in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM]:
            for pattern in RISK_PATTERNS.get(level, []):
                if _matches_phrase(action_lower, pattern):
                    return level
            for word in RISK_WORD_PATTERNS.get(level, []):
                if _matches_word(action_lower, word):
                    return level
        return RiskLevel.LOW

    def get_permission(self, action: str) -> PermissionLevel:
        """Get permission level for an action"""
        action_lower = action.lower()

        # Check explicit user-configured danger words (word-boundary matched to avoid
        # false positives, e.g. "deploy" matching inside "deployment_notes.md")
        for danger in config.require_approval_for:
            danger_lower = danger.lower()
            if " " in danger_lower or any(c in danger_lower for c in "-/><|&"):
                # Multi-word or special-char phrase: safe to substring match
                if danger_lower in action_lower:
                    return PermissionLevel.REQUIRE_APPROVAL
            else:
                if _matches_word(action_lower, danger_lower):
                    return PermissionLevel.REQUIRE_APPROVAL

        risk = self.assess_risk(action)
        if risk == RiskLevel.CRITICAL:
            return PermissionLevel.REQUIRE_APPROVAL
        if risk == RiskLevel.HIGH:
            return PermissionLevel.REQUIRE_APPROVAL
        if risk == RiskLevel.MEDIUM:
            return PermissionLevel.REQUIRE_APPROVAL

        return PermissionLevel.ALLOW

    def _hash_action(self, action: str) -> str:
        return hashlib.sha256(action.encode()).hexdigest()[:16]

    async def check_and_approve(self, action: str, description: str = "",
                                 context: Optional[Dict] = None) -> bool:
        """Check if action is allowed, requesting approval if needed"""
        permission = self.get_permission(action)

        if permission == PermissionLevel.DENY:
            logger.warning("action_denied", action=action[:100])
            return False

        if permission == PermissionLevel.ALLOW:
            return True

        # Require approval
        action_hash = self._hash_action(action)

        if action_hash in self._approved_hashes:
            return True

        if self._approval_callback:
            approved = await self._approval_callback(
                action=action,
                description=description,
                risk=self.assess_risk(action).value,
                context=context or {},
            )
            if approved:
                self._approved_hashes.add(action_hash)
            return approved

        # No callback - default deny for dangerous actions
        logger.warning("action_needs_approval_no_callback", action=action[:100])
        return False

    def add_rule(self, pattern: str, permission: PermissionLevel):
        """Add a custom permission rule"""
        self._permissions[pattern.lower()] = permission

    def audit_log(self, action: str, approved: bool, agent: str = ""):
        """Log security decisions"""
        logger.info(
            "security_audit",
            action=action[:100],
            approved=approved,
            agent=agent,
            risk=self.assess_risk(action).value,
        )


class Sandbox:
    """Code execution sandbox"""

    def __init__(self):
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        import subprocess
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    async def run_python(self, code: str, timeout: int = 30,
                          packages: Optional[List[str]] = None) -> Dict:
        """Run Python code in isolated environment"""
        if self.docker_available and config.sandbox_enabled:
            return await self._run_in_docker(code, "python", timeout, packages)
        else:
            return await self._run_subprocess_python(code, timeout)

    async def _run_subprocess_python(self, code: str, timeout: int) -> Dict:
        import tempfile
        from pathlib import Path
        from omega.tools.process_utils import run_shell_with_timeout

        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "code.py"
            code_file.write_text(code)

            result = await run_shell_with_timeout(
                f"python3 {code_file}", cwd=tmpdir, timeout=timeout
            )
            return {
                "success": result["success"],
                "stdout": result["output"],
                "stderr": result["error"],
                "returncode": result["returncode"],
            }

    async def _run_in_docker(self, code: str, language: str,
                              timeout: int, packages: Optional[List[str]] = None) -> Dict:
        """Run code inside a Docker container"""
        import tempfile
        import uuid
        from pathlib import Path
        from omega.tools.process_utils import run_shell_with_timeout

        image = config.docker_sandbox_image
        container_name = f"omega-sandbox-{uuid.uuid4().hex[:12]}"

        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "code.py"
            code_file.write_text(code)

            install_cmd = ""
            if packages:
                install_cmd = f"pip install {' '.join(packages)} -q && "

            # Named container so we can force-remove it even if the wrapper
            # process is killed before --rm has a chance to clean up.
            docker_cmd = (
                f"docker run --rm --name {container_name} --network none "
                f"--memory 256m --cpus 0.5 "
                f"-v {tmpdir}:/code "
                f"{image} "
                f"sh -c '{install_cmd}python3 /code/code.py'"
            )

            try:
                result = await asyncio.wait_for(
                    run_shell_with_timeout(docker_cmd, timeout=timeout + 30),
                    timeout=timeout + 35,
                )
                return {
                    "success": result["success"],
                    "stdout": result["output"],
                    "stderr": result["error"],
                    "returncode": result["returncode"],
                    "sandboxed": True,
                }
            finally:
                # Best-effort cleanup: if the container is still running (e.g. the
                # wrapper shell was killed before --rm fired), force-remove it so
                # we don't leak a running sandboxed container on the host.
                cleanup = await run_shell_with_timeout(
                    f"docker rm -f {container_name}", timeout=10
                )
                if not cleanup["success"] and "No such container" not in cleanup["error"]:
                    logger.warning("sandbox_container_cleanup_failed",
                                   container=container_name, error=cleanup["error"])


# Global instances
security = SecurityManager()
sandbox = Sandbox()
