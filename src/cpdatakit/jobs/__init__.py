"""In-process cooperative jobs for local application workflows."""

from .manager import JobHandle, JobManager, JobRecord, JobStatus

__all__ = ["JobHandle", "JobManager", "JobRecord", "JobStatus"]
