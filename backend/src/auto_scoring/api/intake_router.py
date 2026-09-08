"""HTTP boundary for batch intake planning and classification (Issue #101).

Thin per ``AGENTS.md`` "Architecture": every handler validates its input,
calls into the domain/adapters, and translates the result.

* ``GET`` / ``PUT /intake-templates`` -- the reusable 取込の型 the settings
  screen edits.
* ``POST /intake/plan`` -- **a listing goes in, a plan comes out. No file
  bytes.** The app scans the chosen folder and sends names, sizes and content
  digests; the rules assign what they can, and the response says how many
  files would still need an LLM call and how many are already cached. This is
  what the pre-flight "how many calls, roughly how much" number is built from
  (acceptance criterion 7), and it costs nothing to ask.
* ``POST /intake/classify`` -- **one file per request**, and only for files
  the rules did not match. One-at-a-time is what makes progress, partial
  results and cancellation work with nothing but ordinary HTTP: the app shows
  "12 / 30", fills each row as it resolves, and a cancel simply stops issuing
  requests. Everything resolved so far is kept and cached.
* ``GET /intake/classification-availability`` -- whether this host can
  classify at all, and if not, why. Mirrors ``GET /grading/availability``:
  the screen says so and keeps the manual path rather than failing per file.

**Writing is not here.** Once a plan is confirmed, the app calls the
endpoints that already exist -- ``POST /tests`` for a new test, ``POST
/tests/{id}/materials`` and ``POST /submissions`` for an existing one -- one
at a time. That is deliberate: a single "commit the whole batch" endpoint
would make a 27-of-30 failure indistinguishable from a total one, and Issue
#101 requires the successful part to survive.

**Nothing here is logged.** A ``relative_path`` carries the school's course
names, and a page image is its copyrighted material. Requests and responses
alike stay out of log lines, exception messages and recorded datasets (the
rule Issue #35 established for provider payloads).
"""

from __future__ import annotations

import hashlib
import threading
from asyncio import to_thread
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from auto_scoring.adapters.local.classification_cache import ClassificationCache
from auto_scoring.adapters.local.intake_template_store import IntakeTemplateStore
from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.domain.ai_provider import ProviderFailure
from auto_scoring.domain.intake_plan import (
    ClassificationNeed,
    IntakePlan,
    PlannedFile,
    PlannedGroup,
    RoleSource,
    build_plan,
)
from auto_scoring.domain.intake_template import (
    IntakeRule,
    IntakeTemplate,
    IntakeTemplateError,
    MaterialRole,
    Requirement,
    RuleScope,
    ScannedFile,
)
from auto_scoring.domain.material_classifier import (
    AttributionCandidate,
    ClassifierUnavailable,
    MaterialClassifier,
)
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_intake import IntakeLimits, PdfIntakeError

#: Upper bound on how many files one plan request may describe. A real batch
#: is ~70 files; this leaves room for a much larger one while keeping a
#: malformed or hostile request from making the sidecar walk an unbounded
#: list (`AGENTS.md`: validate every input that crosses a trust boundary).
MAX_SCANNED_FILES = 5000

#: Upper bound on candidates offered for one attribution question. Past this
#: the multiple-choice framing stops meaning anything -- and the reviewer's
#: own narrowing step exists precisely so the list stays short.
MAX_ATTRIBUTION_CANDIDATES = 100

#: Render scale for the page image sent to a classifier. Enough for a model
#: to read a printed header, small enough that one call is not dominated by
#: image tokens.
_CLASSIFY_RENDER_SCALE = 1.5

_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

#: How the router obtains a classifier. Called per request rather than once
#: at startup, so an operator who fixes their credentials does not have to
#: restart the app -- and raising `ClassifierUnavailable` is a normal result,
#: not an error (see `build_intake_router`).
ClassifierFactory = Callable[[], MaterialClassifier]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class IntakeRuleModel(BaseModel):
    scope: RuleScope
    pattern: str
    role: MaterialRole
    requirement: Requirement = Requirement.OPTIONAL

    def to_domain(self) -> IntakeRule:
        return IntakeRule(
            scope=self.scope,
            pattern=self.pattern,
            role=self.role,
            requirement=self.requirement,
        )

    @classmethod
    def from_domain(cls, rule: IntakeRule) -> IntakeRuleModel:
        return cls(
            scope=rule.scope,
            pattern=rule.pattern,
            role=rule.role,
            requirement=rule.requirement,
        )


class IntakeTemplateModel(BaseModel):
    id: str
    name: str
    rules: list[IntakeRuleModel]
    split_child_directories: bool = True

    def to_domain(self) -> IntakeTemplate:
        return IntakeTemplate(
            id=self.id,
            name=self.name,
            rules=tuple(rule.to_domain() for rule in self.rules),
            split_child_directories=self.split_child_directories,
        )

    @classmethod
    def from_domain(cls, template: IntakeTemplate) -> IntakeTemplateModel:
        return cls(
            id=template.id,
            name=template.name,
            rules=[IntakeRuleModel.from_domain(rule) for rule in template.rules],
            split_child_directories=template.split_child_directories,
        )


class SaveTemplatesRequest(BaseModel):
    # Required, no default: replacing every template with an empty list must
    # be a deliberate act, not an accidentally-omitted field.
    templates: list[IntakeTemplateModel]


class ScannedFileModel(BaseModel):
    relative_path: str
    size_bytes: int = Field(ge=0)
    sha256: str

    def to_domain(self) -> ScannedFile:
        return ScannedFile(
            relative_path=self.relative_path,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
        )


class PlanRequest(BaseModel):
    template_id: str
    root_name: str
    files: list[ScannedFileModel]


class PlannedFileModel(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int
    role: MaterialRole | None
    role_source: RoleSource
    classification: ClassificationNeed

    @classmethod
    def from_domain(cls, planned: PlannedFile) -> PlannedFileModel:
        return cls(
            relative_path=planned.relative_path,
            sha256=planned.sha256,
            size_bytes=planned.size_bytes,
            role=planned.role,
            role_source=planned.role_source,
            classification=planned.classification,
        )


class PlannedGroupModel(BaseModel):
    key: str
    suggested_name: str
    files: list[PlannedFileModel]
    missing_required_roles_if_new: list[MaterialRole]

    @classmethod
    def from_domain(cls, group: PlannedGroup) -> PlannedGroupModel:
        return cls(
            key=group.key,
            suggested_name=group.suggested_name,
            files=[PlannedFileModel.from_domain(planned) for planned in group.files],
            missing_required_roles_if_new=list(group.missing_required_roles_if_new),
        )


class ClassificationEstimateModel(BaseModel):
    """What the confirmation screen shows *before* anything is sent.

    ``pending`` is the only number that costs money. ``not_needed`` is what a
    template's rules already covered for free -- acceptance criterion 8 is
    that those files are never sent at all, and this is the number that makes
    that visible to the reviewer rather than only true in the code.
    """

    pending: int
    cached: int
    unsupported: int
    not_needed: int


class IntakePlanResponse(BaseModel):
    groups: list[PlannedGroupModel]
    estimate: ClassificationEstimateModel

    @classmethod
    def from_domain(cls, plan: IntakePlan) -> IntakePlanResponse:
        return cls(
            groups=[PlannedGroupModel.from_domain(group) for group in plan.groups],
            estimate=ClassificationEstimateModel(
                pending=plan.estimate.pending,
                cached=plan.estimate.cached,
                unsupported=plan.estimate.unsupported,
                not_needed=plan.estimate.not_needed,
            ),
        )


class RoleProposalResponse(BaseModel):
    """``role`` is ``null`` when the classifier could not tell.

    That is a real answer, not a failure: the reviewer picks, exactly as they
    would for a file no rule matched.
    """

    role: MaterialRole | None
    confidence: float
    cached: bool


class AttributionProposalResponse(BaseModel):
    """``test_id`` is ``null`` for "could not tell".

    Expect that often. The observed answer sheets carry a course-name field
    that is printed on some, blank on others and handwritten on the rest, and
    every sheet inspected had blank student name/id fields -- so a first page
    frequently identifies nothing at all.
    """

    test_id: str | None
    confidence: float


class ClassificationAvailabilityResponse(BaseModel):
    available: bool
    #: Present only when unavailable. Safe to display: it names configuration
    #: *variables* and transport ids, never a configured value.
    reason: str | None = None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _read_upload_within_limit(file: UploadFile, max_size_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"file size exceeds limit {max_size_bytes}",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def build_intake_router(
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    classifier_factory: ClassifierFactory,
    *,
    intake_limits: IntakeLimits | None = None,
    pdfium_lock: threading.Lock | None = None,
) -> APIRouter:
    """Build the router.

    ``classifier_factory`` is a zero-argument callable returning a
    `MaterialClassifier`, or raising `ClassifierUnavailable`. Injected rather
    than reached for so a test can state which world it is in (``AGENTS.md``:
    inject boundaries from outside the core) -- and called per request, not
    once at startup, so an operator who fixes their credentials does not have
    to restart the app to use them.

    ``pdfium_lock`` must be the same lock the rest of the app serializes
    PDFium on: pypdfium2 is not safe to call concurrently from several
    threads of one process, and the app deliberately issues a few
    classification requests at once.
    """
    limits = intake_limits or IntakeLimits()
    lock = pdfium_lock or threading.Lock()
    templates = IntakeTemplateStore(store.root)
    cache = ClassificationCache(store.root)
    router = APIRouter(tags=["intake"])

    def _render_first_page(data: bytes) -> bytes:
        """The first page of ``data`` as a PNG.

        Only the first page is ever rendered -- Issue #101's cost rule. The
        bytes are written to a scratch file because `PdfEngine` works on
        paths, and the scratch directory is removed before this returns.
        """
        with TemporaryDirectory(prefix="auto-scoring-classify-") as scratch_dir:
            scratch = Path(scratch_dir) / "page.pdf"
            scratch.write_bytes(data)
            with lock:
                return pdf_engine.render_page_png(scratch, 0, scale=_CLASSIFY_RENDER_SCALE)

    @router.get("/intake-templates", response_model=list[IntakeTemplateModel])
    def list_templates() -> list[IntakeTemplateModel]:
        try:
            saved = templates.load()
        except IntakeTemplateError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return [IntakeTemplateModel.from_domain(template) for template in saved]

    @router.put("/intake-templates", response_model=list[IntakeTemplateModel])
    def save_templates(request: SaveTemplatesRequest) -> list[IntakeTemplateModel]:
        try:
            saved = [template.to_domain() for template in request.templates]
            templates.save(saved)
        except IntakeTemplateError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        return [IntakeTemplateModel.from_domain(template) for template in saved]

    @router.post("/intake/plan", response_model=IntakePlanResponse)
    def plan_intake(request: PlanRequest) -> IntakePlanResponse:
        if len(request.files) > MAX_SCANNED_FILES:
            raise HTTPException(
                422, detail=f"a plan may describe at most {MAX_SCANNED_FILES} files"
            )
        template = templates.get(request.template_id)
        if template is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"intake template {request.template_id!r} not found",
            )
        try:
            scanned = [entry.to_domain() for entry in request.files]
        except IntakeTemplateError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        plan = build_plan(
            scanned,
            template,
            root_name=request.root_name,
            cached_digests=cache.cached_digests(),
        )
        return IntakePlanResponse.from_domain(plan)

    @router.get(
        "/intake/classification-availability", response_model=ClassificationAvailabilityResponse
    )
    def classification_availability() -> ClassificationAvailabilityResponse:
        try:
            classifier_factory()
        except ClassifierUnavailable as exc:
            return ClassificationAvailabilityResponse(available=False, reason=exc.reason)
        return ClassificationAvailabilityResponse(available=True)

    @router.post("/intake/classify", response_model=RoleProposalResponse)
    async def classify_material(file: UploadFile = File(...)) -> RoleProposalResponse:
        """Propose what one file is, from its first page.

        Callers send only files a template's rules did not match: a matched
        file must never reach this endpoint (acceptance criterion 8). Nothing
        here enforces that -- there is no way for this endpoint to know which
        template the caller used -- so the guarantee lives where the decision
        is made, in `domain.intake_plan.build_plan` and its tests.
        """
        data = await _read_upload_within_limit(file, limits.max_size_bytes)
        digest = _digest(data)
        hit, cached_role = cache.get_role(digest)
        if hit:
            # A cached proposal is still only a proposal: it goes through the
            # same confirmation step a fresh one does. What the cache saves
            # is the call, not the review.
            return RoleProposalResponse(role=cached_role, confidence=0.0, cached=True)

        try:
            classifier = classifier_factory()
        except ClassifierUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.reason) from exc
        try:
            image = await to_thread(_render_first_page, data)
        except PdfIntakeError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        except Exception as exc:
            # Anything pdfium raises on a file that is not a readable PDF.
            # The message is this repository's own text -- an exception from
            # a parser can quote the document's bytes.
            raise HTTPException(
                400, detail=f"the first page could not be rendered: {type(exc).__name__}"
            ) from exc
        try:
            proposal = await to_thread(classifier.classify_role, image)
        except ProviderFailure as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, detail=f"classification failed: {exc}"
            ) from exc

        cache.put_role(digest, proposal.role)
        return RoleProposalResponse(
            role=proposal.role, confidence=proposal.confidence, cached=False
        )

    @router.post("/intake/attribute", response_model=AttributionProposalResponse)
    async def attribute_answer(
        file: UploadFile = File(...),
        candidate_ids: list[str] = Form(...),
        candidate_labels: list[str] = Form(...),
    ) -> AttributionProposalResponse:
        """Ask which of the offered tests one answer belongs to.

        The candidate set is the caller's: the tests this batch would create
        plus the already-registered ones the reviewer has narrowed to. **A
        caller with a single candidate must not call this at all** -- the
        reviewer has already decided, and asking a provider to choose from a
        list of one spends money to confirm a foregone conclusion. That is
        the ordinary case from week two onward, which is why the reviewer's
        narrowing step is the real cost control here and the classifier is
        the fallback.
        """
        if len(candidate_ids) != len(candidate_labels):
            raise HTTPException(
                422, detail="candidate_ids and candidate_labels must be the same length"
            )
        if len(candidate_ids) < 2:
            raise HTTPException(
                422,
                detail=(
                    "attribution needs at least two candidates; with one the answer is "
                    "already decided and no call should be made"
                ),
            )
        if len(candidate_ids) > MAX_ATTRIBUTION_CANDIDATES:
            raise HTTPException(
                422,
                detail=f"at most {MAX_ATTRIBUTION_CANDIDATES} candidates may be offered",
            )
        try:
            candidates = [
                AttributionCandidate(id=candidate_id, label=label)
                for candidate_id, label in zip(candidate_ids, candidate_labels, strict=True)
            ]
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

        data = await _read_upload_within_limit(file, limits.max_size_bytes)
        try:
            classifier = classifier_factory()
        except ClassifierUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.reason) from exc
        try:
            image = await to_thread(_render_first_page, data)
        except Exception as exc:
            raise HTTPException(
                400, detail=f"the first page could not be rendered: {type(exc).__name__}"
            ) from exc
        try:
            proposal = await to_thread(classifier.attribute_answer, image, candidates)
        except ProviderFailure as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, detail=f"attribution failed: {exc}"
            ) from exc
        return AttributionProposalResponse(
            test_id=proposal.candidate_id, confidence=proposal.confidence
        )

    return router
