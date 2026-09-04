"""Adapters: concrete implementations of the domain ports.

Adapters depend on `domain` and on `auto_scoring.db` (the ORM), never the
reverse. Dependency direction across the backend:
``api -> adapters -> db -> domain``.
"""

from auto_scoring.adapters.atomic import StagedFiles, transactional_operation
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.purge import purge_submission, purge_test
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "InMemoryScoreRepository",
    "LocalFileStore",
    "SqlAlchemyUnitOfWork",
    "StagedFiles",
    "purge_submission",
    "purge_test",
    "transactional_operation",
]
