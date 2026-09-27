"""
Database module for CUA-Sentinel.
Exports database connection getters, transaction utilities, and typed repositories.
"""

try:
    from .connections import (
        OPERATIONAL_DB,
        AUDIT_DB,
        KNOWLEDGE_DB,
        STATE_DB,
        get_operational_db,
        get_audit_db,
        get_knowledge_db,
        get_state_db,
        initialize_all_databases,
    )
    from .transaction import (
        DatabaseLockError,
        execute_write_transaction,
        run_write_with_retry,
    )
    from .repositories import (
        OperationalRepository,
        AuditRepository,
        KnowledgeRepository,
        BaseRepository,
    )
except ImportError:
    from backend.db.connections import (
        OPERATIONAL_DB,
        AUDIT_DB,
        KNOWLEDGE_DB,
        STATE_DB,
        get_operational_db,
        get_audit_db,
        get_knowledge_db,
        get_state_db,
        initialize_all_databases,
    )
    from backend.db.transaction import (
        DatabaseLockError,
        execute_write_transaction,
        run_write_with_retry,
    )
    from backend.db.repositories import (
        OperationalRepository,
        AuditRepository,
        KnowledgeRepository,
        BaseRepository,
    )

__all__ = [
    "OPERATIONAL_DB",
    "AUDIT_DB",
    "KNOWLEDGE_DB",
    "STATE_DB",
    "get_operational_db",
    "get_audit_db",
    "get_knowledge_db",
    "get_state_db",
    "initialize_all_databases",
    "DatabaseLockError",
    "execute_write_transaction",
    "run_write_with_retry",
    "OperationalRepository",
    "AuditRepository",
    "KnowledgeRepository",
    "BaseRepository",
]
