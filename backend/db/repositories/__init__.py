"""
Repository layer for CUA-Sentinel databases.
Exports OperationalRepository, AuditRepository, KnowledgeRepository, and BaseRepository.
"""

try:
    from .base import BaseRepository
    from .operational_repo import OperationalRepository
    from .audit_repo import AuditRepository
    from .knowledge_repo import KnowledgeRepository
    from ..transaction import DatabaseLockError, execute_write_transaction, run_write_with_retry
except ImportError:
    from backend.db.repositories.base import BaseRepository
    from backend.db.repositories.operational_repo import OperationalRepository
    from backend.db.repositories.audit_repo import AuditRepository
    from backend.db.repositories.knowledge_repo import KnowledgeRepository
    from backend.db.transaction import DatabaseLockError, execute_write_transaction, run_write_with_retry

__all__ = [
    "BaseRepository",
    "OperationalRepository",
    "AuditRepository",
    "KnowledgeRepository",
    "DatabaseLockError",
    "execute_write_transaction",
    "run_write_with_retry",
]
