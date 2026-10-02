from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class LocalJobDispatcher:
    """One process only. Durable state is in SQLite, not this executor."""

    def __init__(self, process: Callable[[str, str], None]):
        self.process = process
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="clearpath-demo"
        )

    def dispatch(self, case_id: str, run_id: str) -> None:
        self.executor.submit(self.process, case_id, run_id)

    def close(self) -> None:
        self.executor.shutdown(wait=True)
