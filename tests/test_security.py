"""Tests for omega.security.manager"""

import pytest
from omega.security.manager import SecurityManager, RiskLevel, PermissionLevel


class TestRiskAssessment:
    def setup_method(self):
        self.security = SecurityManager()

    def test_safe_commands_are_low_risk(self):
        for cmd in ["ls -la", "echo hello", "pwd", "git status"]:
            assert self.security.assess_risk(cmd) == RiskLevel.LOW

    def test_rm_rf_root_is_critical(self):
        assert self.security.assess_risk("rm -rf /") == RiskLevel.CRITICAL

    def test_rm_rf_absolute_path_is_critical(self):
        assert self.security.assess_risk("rm -rf /tmp/foo") == RiskLevel.CRITICAL

    def test_rm_rf_relative_path_is_high_not_critical(self):
        assert self.security.assess_risk("rm -rf ./build") == RiskLevel.HIGH

    def test_git_push_is_high_risk(self):
        assert self.security.assess_risk("git push origin main") == RiskLevel.HIGH

    def test_git_force_push_is_critical(self):
        assert self.security.assess_risk("git push --force origin main") == RiskLevel.CRITICAL

    def test_git_commit_is_medium_risk(self):
        assert self.security.assess_risk("git commit -m 'fix'") == RiskLevel.MEDIUM

    def test_format_word_does_not_false_positive_on_filename(self):
        """Regression test: 'format' substring inside a filename should not trigger CRITICAL"""
        assert self.security.assess_risk("python format_string_helper.py") == RiskLevel.LOW

    def test_format_as_standalone_word_is_critical(self):
        assert self.security.assess_risk("format C: drive") == RiskLevel.CRITICAL

    def test_deployment_notes_does_not_match_deploy(self):
        """Regression test: filenames containing risk words as substrings shouldn't trigger"""
        assert self.security.assess_risk("cat deployment_notes.md") == RiskLevel.LOW


class TestPermissions:
    def setup_method(self):
        self.security = SecurityManager()

    def test_safe_command_allowed(self):
        assert self.security.get_permission("ls -la") == PermissionLevel.ALLOW

    def test_dangerous_command_requires_approval(self):
        assert self.security.get_permission("rm -rf /") == PermissionLevel.REQUIRE_APPROVAL

    def test_push_requires_approval(self):
        assert self.security.get_permission("git push origin main") == PermissionLevel.REQUIRE_APPROVAL

    def test_filename_with_deploy_substring_not_blocked(self):
        """'deploy' is in require_approval_for; ensure word-boundary matching prevents
        false positives on filenames like 'deployment_notes.md'"""
        assert self.security.get_permission("cat deployment_notes.md") == PermissionLevel.ALLOW


class TestApprovalFlow:
    @pytest.mark.asyncio
    async def test_approval_granted_when_callback_approves(self):
        async def approve_all(**kwargs):
            return True

        security = SecurityManager(approval_callback=approve_all)
        result = await security.check_and_approve("rm -rf /tmp/test")
        assert result is True

    @pytest.mark.asyncio
    async def test_approval_denied_when_callback_denies(self):
        async def deny_all(**kwargs):
            return False

        security = SecurityManager(approval_callback=deny_all)
        result = await security.check_and_approve("rm -rf /tmp/test")
        assert result is False

    @pytest.mark.asyncio
    async def test_safe_action_allowed_without_callback(self):
        security = SecurityManager(approval_callback=None)
        result = await security.check_and_approve("ls -la")
        assert result is True

    @pytest.mark.asyncio
    async def test_dangerous_action_denied_without_callback(self):
        security = SecurityManager(approval_callback=None)
        result = await security.check_and_approve("rm -rf /")
        assert result is False

    @pytest.mark.asyncio
    async def test_approved_action_is_cached(self):
        call_count = 0

        async def approve_once(**kwargs):
            nonlocal call_count
            call_count += 1
            return True

        security = SecurityManager(approval_callback=approve_once)
        action = "rm -rf /tmp/cached_test"
        await security.check_and_approve(action)
        await security.check_and_approve(action)
        assert call_count == 1  # second call should use cached approval
