"""Error classes. Every error carries a code, a message and the next step for the user."""

from __future__ import annotations


class FaultSageError(Exception):
    code = "internal_error"
    status = 500

    def __init__(self, message: str, next_step: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.next_step = next_step

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {"error": {"code": self.code, "message": self.message, "next_step": self.next_step}}


class NotFoundError(FaultSageError):
    code = "not_found"
    status = 404


class ValidationFailedError(FaultSageError):
    code = "validation_failed"
    status = 422


class UnauthorisedError(FaultSageError):
    code = "unauthorised"
    status = 401


class ForbiddenOriginError(FaultSageError):
    code = "forbidden_origin"
    status = 403


class PatchStaleError(FaultSageError):
    code = "patch_stale"
    status = 409


class GitDirtyError(FaultSageError):
    code = "git_dirty"
    status = 409


class PathOutsideProjectError(FaultSageError):
    code = "path_outside_project"
    status = 400


class VerifyRunningError(FaultSageError):
    code = "verify_running"
    status = 409


class DaemonPausedError(FaultSageError):
    code = "daemon_paused"
    status = 409


class DbBusyError(FaultSageError):
    code = "db_busy"
    status = 503


class ConfigError(FaultSageError):
    code = "validation_failed"
    status = 422


class ProjectNotFoundError(FaultSageError):
    code = "not_found"
    status = 404


class DestructiveMigrationError(FaultSageError):
    """Raised when a destructive migration is pending and has not been approved (SR-26)."""

    code = "destructive_migration_pending"
    status = 409


class PlanLimitError(FaultSageError):
    code = "plan_limit"
    status = 402


class RateLimitedError(FaultSageError):
    code = "rate_limited"
    status = 429


class ForbiddenError(FaultSageError):
    code = "forbidden"
    status = 403
