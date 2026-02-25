"""JobStore Protocol defining the contract for all storage backends."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class JobStore(Protocol):
    """Protocol that all job storage backends must satisfy."""

    def create_job(self, job_id: str, estimated_remaining_seconds: Optional[float] = None) -> Dict[str, Any]: ...

    def update_job(self, job_id: str, **kwargs: Any) -> None: ...

    def get_job(self, job_id: str) -> Dict[str, Any]: ...

    def job_exists(self, job_id: str) -> bool: ...

    def delete_job(self, job_id: str) -> None: ...

    def record_progress(self, job_id: str, message: Optional[str], metrics: Dict[str, Any]) -> None: ...

    def get_progress_events(self, job_id: str) -> List[Dict[str, Any]]: ...

    def get_progress_count(self, job_id: str) -> int: ...

    def append_log(
        self,
        job_id: str,
        *,
        level: str,
        logger_name: str,
        message: str,
        timestamp: Optional[datetime] = None,
    ) -> None: ...

    def get_logs(
        self,
        job_id: str,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        level: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    def get_log_count(self, job_id: str, *, level: Optional[str] = None) -> int: ...

    def set_payload_overview(self, job_id: str, overview: Dict[str, Any]) -> None: ...

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        username: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]: ...

    def count_jobs(
        self,
        *,
        status: Optional[str] = None,
        username: Optional[str] = None,
        job_type: Optional[str] = None,
    ) -> int: ...

    def recover_orphaned_jobs(self) -> int: ...

    def recover_pending_jobs(self) -> List[str]: ...
