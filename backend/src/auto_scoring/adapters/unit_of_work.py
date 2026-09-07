"""SQLAlchemy Unit of Work: one ``Session``, one transaction boundary.

Usage::

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(test)
        uow.submissions.add(submission)
        uow.commit()

Leaving the block without :meth:`commit` rolls everything back, so a failure
half-way through never leaves a partial write (issue #11 verification:
"transaction 失敗時に … 中途半端な状態が残らない").
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.sqlalchemy_repositories import (
    SqlAlchemyAnnotationRepository,
    SqlAlchemyAnswerImageRepository,
    SqlAlchemyDependencyGraphRepository,
    SqlAlchemyExportRepository,
    SqlAlchemyGradeResultRepository,
    SqlAlchemyJobRepository,
    SqlAlchemyQuestionRepository,
    SqlAlchemyRecognitionResultRepository,
    SqlAlchemyReviewRepository,
    SqlAlchemyRubricRepository,
    SqlAlchemySubmissionRepository,
    SqlAlchemyTestRepository,
)


class SqlAlchemyUnitOfWork:
    """Concrete :class:`auto_scoring.domain.repositories.UnitOfWork`."""

    tests: SqlAlchemyTestRepository
    questions: SqlAlchemyQuestionRepository
    rubrics: SqlAlchemyRubricRepository
    submissions: SqlAlchemySubmissionRepository
    answer_images: SqlAlchemyAnswerImageRepository
    recognitions: SqlAlchemyRecognitionResultRepository
    grades: SqlAlchemyGradeResultRepository
    annotations: SqlAlchemyAnnotationRepository
    reviews: SqlAlchemyReviewRepository
    jobs: SqlAlchemyJobRepository
    exports: SqlAlchemyExportRepository
    dependency_graphs: SqlAlchemyDependencyGraphRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        session = self._session
        self.tests = SqlAlchemyTestRepository(session)
        self.questions = SqlAlchemyQuestionRepository(session)
        self.rubrics = SqlAlchemyRubricRepository(session)
        self.submissions = SqlAlchemySubmissionRepository(session)
        self.answer_images = SqlAlchemyAnswerImageRepository(session)
        self.recognitions = SqlAlchemyRecognitionResultRepository(session)
        self.grades = SqlAlchemyGradeResultRepository(session)
        self.annotations = SqlAlchemyAnnotationRepository(session)
        self.reviews = SqlAlchemyReviewRepository(session)
        self.jobs = SqlAlchemyJobRepository(session)
        self.exports = SqlAlchemyExportRepository(session)
        self.dependency_graphs = SqlAlchemyDependencyGraphRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self.session.rollback()
        finally:
            self.session.close()
            self._session = None

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def flush(self) -> None:
        """Send pending INSERTs to the DB (surfacing constraint errors) without committing."""
        self.session.flush()

    @property
    def session(self) -> Session:
        """The active SQLAlchemy session (raises if used outside the context manager)."""
        if self._session is None:
            raise RuntimeError("unit of work is not active; use it as a context manager")
        return self._session
