import time
import unittest

from APP import jobs
from APP.jobs import JobStore


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = JobStore()

    def test_new_job_starts_queued(self):
        job = self.store.create("owner-1", "a.pdf")
        self.assertEqual(job.status, jobs.QUEUED)
        self.assertIsNone(job.result)
        self.assertIsNone(job.error)

    def test_owner_can_read_own_job(self):
        job = self.store.create("owner-1", "a.pdf")
        self.assertIsNotNone(self.store.get(job.id, "owner-1"))

    def test_other_owner_cannot_read_job(self):
        # Security-relevant: a job id must not act as a bearer capability that
        # exposes another user's filenames or ingest results. The route turns
        # this None into the same 404 an unknown id gets, so the two are
        # indistinguishable to a prober.
        job = self.store.create("owner-1", "secret-contract.pdf")
        self.assertIsNone(self.store.get(job.id, "owner-2"))

    def test_unknown_job_is_none(self):
        self.assertIsNone(self.store.get("no-such-id", "owner-1"))

    def test_mark_records_result_and_status(self):
        job = self.store.create("owner-1", "a.pdf")
        self.store.mark(job.id, jobs.RUNNING)
        self.assertEqual(self.store.get(job.id, "owner-1").status, jobs.RUNNING)

        self.store.mark(job.id, jobs.SUCCEEDED, result={"chunks": 190})
        stored = self.store.get(job.id, "owner-1")
        self.assertEqual(stored.status, jobs.SUCCEEDED)
        self.assertEqual(stored.result, {"chunks": 190})

    def test_mark_records_failure_reason(self):
        job = self.store.create("owner-1", "a.pdf")
        self.store.mark(job.id, jobs.FAILED, error="no text could be extracted")
        stored = self.store.get(job.id, "owner-1")
        self.assertEqual(stored.status, jobs.FAILED)
        self.assertIn("no text", stored.error)

    def test_mark_unknown_job_is_a_noop(self):
        self.store.mark("no-such-id", jobs.SUCCEEDED)  # must not raise

    def test_finished_jobs_are_evicted_after_retention(self):
        old = self.store.create("owner-1", "old.pdf")
        self.store.mark(old.id, jobs.SUCCEEDED, result={})
        # Backdate past the retention window rather than sleeping an hour.
        self.store._jobs[old.id].updated_at = time.time() - (jobs.RETENTION_SECONDS + 60)

        self.store.create("owner-1", "new.pdf")  # create() triggers eviction
        self.assertIsNone(self.store.get(old.id, "owner-1"))

    def test_eviction_never_drops_in_flight_jobs(self):
        # A running ingest that outlives the retention window must survive:
        # losing it would strand a client polling for a result that still
        # arrives.
        running = self.store.create("owner-1", "slow.pdf")
        self.store.mark(running.id, jobs.RUNNING)
        self.store._jobs[running.id].updated_at = time.time() - (jobs.RETENTION_SECONDS + 60)

        self.store.create("owner-1", "new.pdf")
        self.assertIsNotNone(self.store.get(running.id, "owner-1"))

    def test_hard_cap_prunes_terminal_jobs_only(self):
        keep = self.store.create("owner-1", "running.pdf")
        self.store.mark(keep.id, jobs.RUNNING)
        for i in range(jobs.MAX_JOBS + 10):
            j = self.store.create("owner-1", f"done-{i}.pdf")
            self.store.mark(j.id, jobs.SUCCEEDED, result={})
        self.assertIsNotNone(self.store.get(keep.id, "owner-1"))
        self.assertLessEqual(len(self.store._jobs), jobs.MAX_JOBS + 1)


if __name__ == "__main__":
    unittest.main()
