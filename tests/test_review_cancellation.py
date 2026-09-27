"""Cancellation preserves a distinguishable diagnostic for actual job failures."""

import logging
import threading

import pytest

from cpdatakit.exceptions import DataReadError
from cpdatakit.jobs import JobManager, JobStatus
from cpdatakit.jobs.manager import JobCancelled


@pytest.mark.parametrize("failure", [ValueError("broken payload"), DataReadError("broken input")])
def test_cancelled_job_retains_failure_diagnostic_and_logs(caplog, failure):
    manager = JobManager(max_workers=1)
    started = threading.Event()
    release = threading.Event()

    def work(cancel):
        started.set()
        release.wait(5)
        assert cancel.is_set()
        raise failure

    try:
        with caplog.at_level(logging.ERROR, logger="cpdatakit.jobs.manager"):
            handle = manager.submit("failing-cancellation", work)
            assert started.wait(5)
            assert manager.cancel(handle.id)
            release.set()
            record = manager.wait(handle.id, timeout=5)
        assert record.status == JobStatus.CANCELLED
        assert record.error is not None
        assert "cancel" in record.error.lower()
        assert record.result is None
        assert record.finished_at is not None
        assert any(item.exc_info and item.exc_info[1] is failure for item in caplog.records)
    finally:
        release.set()
        manager.shutdown()


def test_checkpoint_cancellation_keeps_normal_cancelled_result(caplog):
    manager = JobManager(max_workers=1)
    started = threading.Event()
    release = threading.Event()

    def work(cancel):
        started.set()
        release.wait(5)
        cancel.checkpoint("read next block")

    try:
        handle = manager.submit("cooperative-cancellation", work)
        assert started.wait(5)
        assert manager.cancel(handle.id)
        release.set()
        record = manager.wait(handle.id, timeout=5)
        assert record.status == JobStatus.CANCELLED
        assert record.error is None
        assert record.result is None
        assert not any(item.levelno >= logging.ERROR for item in caplog.records)
        assert not any(
            item.exc_info and isinstance(item.exc_info[1], JobCancelled) for item in caplog.records
        )
    finally:
        release.set()
        manager.shutdown()
