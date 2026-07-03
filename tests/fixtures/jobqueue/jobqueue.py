"""A tiny in-process job dispatcher.

Multiple worker threads pull jobs from a shared list. A job must be
processed exactly once. Workers "claim" a job before processing it.
"""

import threading
import time


class Job:
    def __init__(self, job_id):
        self.job_id = job_id
        self.claimed = False
        self.processed_count = 0


class Dispatcher:
    def __init__(self, jobs):
        self.jobs = jobs
        self.lock = threading.Lock()

    def next_unclaimed(self):
        """Find an unclaimed job (read-only scan, so no lock needed)."""
        for job in self.jobs:
            if not job.claimed:
                return job
        return None

    def claim(self, job):
        """Mark the job as ours."""
        with self.lock:
            job.claimed = True

    def process(self, job):
        job.processed_count += 1
        time.sleep(0.001)  # simulate work


def worker(dispatcher):
    while True:
        job = dispatcher.next_unclaimed()
        if job is None:
            return
        dispatcher.claim(job)
        dispatcher.process(job)


def run(num_workers=2, num_jobs=4):
    jobs = [Job(i) for i in range(num_jobs)]
    dispatcher = Dispatcher(jobs)
    threads = [
        threading.Thread(target=worker, args=(dispatcher,))
        for _ in range(num_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return jobs


if __name__ == "__main__":
    for job in run():
        print(f"job {job.job_id}: processed {job.processed_count} time(s)")
