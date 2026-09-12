"""HTTP boundary for **page images and page geometry** (Issue #207, parent #201).

PoC 6 (`docs/poc-6-pdf-coordinates.md`, Issue #202) chose approach B: the UI
stops receiving raw PDF bytes and rendering them itself, and displays the page
images this sidecar rasterizes with pypdfium2 instead. The reason is not
measured accuracy -- approach A (pdf.js in the renderer) passed all 45 sampled
points too -- it is that **one pdfium does both the rasterization and the
coordinate transform**, so there is no second interpretation of "the displayed
page" for the contract to drift between.

Endpoints:

* ``GET /submissions/{submission_id}/pages/{page_index}/image``
* ``GET /tests/{test_id}/answer-layout/pages/{page_index}/image``
  -- one page rasterized to ``image/png`` at one of `ALLOWED_SCALES`.
* ``GET /submissions/{submission_id}/pages``
* ``GET /tests/{test_id}/answer-layout/pages``
  -- ``page_count`` plus each page's displayed size and rotation.
* ``GET /tests/{test_id}/materials/{material_id}/pages``
* ``GET /tests/{test_id}/materials/{material_id}/pages/{page_index}/image``
  -- the same for a registered material (Issue #415). Only PDF materials can
  be rasterized; a Word/Excel material is refused with 415 rather than served
  as bytes, for the reason §7.5 gives: the renderer never receives a raw
  document. The material list itself is `GET /tests/{test_id}/materials`
  (`api.test_registration_router`), which returns metadata only.

## The image's own pixel size is the only basis for a normalized coordinate

A renderer builds a normalized coordinate from **the returned image's pixel
dimensions and nothing else**::

    normalized_x = click_px / image_width_px
    normalized_y = click_py / image_height_px

pdfium drew the displayed page into exactly those pixels, so this cannot
disagree with `domain.pdf_geometry` by construction.

**The geometry endpoints must not be used for that division.** They exist for
layout decisions taken *before* an image arrives -- reserving a box at the
right aspect ratio, paging (``page_count``), knowing the rotation. Building a
coordinate from the geometry while the image is rounded up separately
(``ceil(displayed x scale)``) rebuilds in the renderer exactly the double
interpretation approach B removed. `_COORDINATE_RULE` repeats this in every
handler's description because that is what reaches the generated client;
`docs/pdf-review-overlay.md` §3.1 carries the same split.

## Why the pixel size is not reported anywhere but in the image

Issue #207 proposed also returning the pixel size, in a response header or in
the geometry payload. It is deliberately **not** returned: a PNG carries its
own dimensions and every renderer reads them (``naturalWidth`` /
``naturalHeight``) without a second request, so a copy of that number would buy
nothing and would be one more value that can disagree with the image -- the
exact shape the rule above exists to prevent. The relationship (pixels =
``ceil(displayed x scale)``) is pinned by `backend/tests/test_page_image_api.py`
so it is not folklore, but the renderer is given one place to read it from.

## The raw-PDF endpoints stay

`GET /submissions/{id}/source-pdf` and `GET /tests/{id}/answer-layout/pdf` are
neither removed nor re-routed -- the Flutter app renders from them until the
Electron cut-over. Their descriptions carry who uses them and where dropping
them is decided (#201).
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi import Path as PathParam
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.domain.material_intake import MaterialIntakeError, material_extension
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import PageGeometry

#: Every render scale a client may ask for, in pixels per PDF point.
#:
#: Enumerated rather than accepted as an arbitrary float because the cost is
#: superlinear in the caller's number and paid in this process's memory: PoC 6
#: measured 5.1 ms/page at 1.0, 20.8 ms at 2.0 and 78.6 ms at 3.5, and nothing
#: stops a caller from asking for 50. A scale outside this set is **rejected**,
#: never quietly snapped to the nearest permitted one -- a substituted scale
#: returns an image whose pixel size is not the one the caller asked for, and
#: the caller has no way to notice.
ALLOWED_SCALES: tuple[float, ...] = (1.0, 2.0, 3.5)

#: PoC 6's own recommendation: legible at 100% zoom, 21 ms/page, 0.36 MiB for a
#: 40-page answer.
DEFAULT_SCALE = 2.0

_ETAG_DIGEST_CHARS = 32

_SCALE_DESCRIPTION = (
    "Pixels per PDF point. Only 1.0, 2.0 and 3.5 are accepted; any other value is rejected "
    "with 422 rather than snapped to a permitted one."
)


def _permitted_scale(scale: float) -> float:
    """Reject any scale outside `ALLOWED_SCALES`, as a 422 naming the set.

    A `Literal[1.0, 2.0, 3.5]` annotation would put the same set in the schema
    with no code at all, but pydantic's literal validator does not coerce the
    string a query parameter actually arrives as: ``?scale=2.0`` is refused
    along with ``?scale=2.5``, while the default -- never parsed from a string
    -- keeps working. Only a test that passes a permitted scale *explicitly*
    catches that.
    """
    if scale not in ALLOWED_SCALES:
        permitted = ", ".join(str(value) for value in ALLOWED_SCALES)
        raise ValueError(f"scale must be one of {permitted}")
    return scale


#: The ``scale`` query parameter. The permitted set reaches the OpenAPI schema
#: -- and so the generated client -- through ``json_schema_extra`` and reaches
#: the request through `_permitted_scale`, both read off `ALLOWED_SCALES`, so
#: the documented set and the enforced set cannot drift apart.
PageImageScale = Annotated[
    float,
    AfterValidator(_permitted_scale),
    Query(description=_SCALE_DESCRIPTION, json_schema_extra={"enum": list(ALLOWED_SCALES)}),
]


class PageGeometryResponse(BaseModel):
    """One page's layout, as pdfium displays it.

    ``displayed_width`` / ``displayed_height`` are
    `domain.pdf_geometry.PageGeometry`'s own properties: ``CropBox``
    intersected with ``MediaBox``, with ``/Rotate`` applied -- the same values
    the annotation export transforms coordinates against.

    **Not a basis for coordinates**; see `_COORDINATE_RULE`.
    """

    page_index: int = Field(description="0-based index of this page.")
    displayed_width: float = Field(
        description=(
            "Width in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after "
            "/Rotate). For sizing a placeholder, not for dividing a click position."
        )
    )
    displayed_height: float = Field(
        description=(
            "Height in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after "
            "/Rotate). For sizing a placeholder, not for dividing a click position."
        )
    )
    rotation: int = Field(description="The page's /Rotate, reduced to 0, 90, 180 or 270.")

    @classmethod
    def from_geometry(cls, page_index: int, geometry: PageGeometry) -> PageGeometryResponse:
        return cls(
            page_index=page_index,
            displayed_width=geometry.displayed_width,
            displayed_height=geometry.displayed_height,
            rotation=geometry.normalized_rotation,
        )


class DocumentPagesResponse(BaseModel):
    """Every page of one stored document, in order."""

    page_count: int = Field(
        description="Number of pages. Valid page_index values are 0 to page_count - 1."
    )
    pages: list[PageGeometryResponse]


#: The one rule a renderer has to follow for approach B to hold, appended to
#: all four handler descriptions. Kept in a single string so the generated
#: client cannot end up carrying two differently-worded versions of it.
_COORDINATE_RULE = """

**A normalized coordinate is built from the returned image's own pixel size,
and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium
drew the displayed page into those pixels, so that division cannot disagree
with this sidecar's coordinate transform.

Do **not** divide by the `displayed_width` / `displayed_height` reported by
`GET .../pages`. The image's pixel size is rounded up independently
(`ceil(displayed x scale)`), so a coordinate taken from the geometry and an
image rounded separately is the double interpretation PoC 6 removed. The
geometry endpoint is for layout before the image arrives (aspect-ratio
placeholders), for paging, and for knowing the rotation.
"""

_LIST_SUBMISSION_PAGES_DESCRIPTION = (
    "Page count, displayed size and rotation of the answer PDF, for laying the viewer out "
    "**before** the page images arrive, and for paging." + _COORDINATE_RULE
)
_LIST_ANSWER_LAYOUT_PAGES_DESCRIPTION = (
    "Page count, displayed size and rotation of the test's answer sheet, for laying the "
    "answer-area editor out **before** the page images arrive, and for paging." + _COORDINATE_RULE
)
_SUBMISSION_PAGE_IMAGE_DESCRIPTION = (
    "One page of the answer PDF, rasterized by the same pdfium that performs the coordinate "
    "transform (PoC 6, approach B)." + _COORDINATE_RULE
)
_ANSWER_LAYOUT_PAGE_IMAGE_DESCRIPTION = (
    "One page of the test's answer sheet, rasterized by the same pdfium that performs the "
    "coordinate transform (PoC 6, approach B)." + _COORDINATE_RULE
)
_MATERIAL_PAGES_DESCRIPTION = (
    "Page count, displayed size and rotation of one registered material, for paging "
    "through it in the material window. Only PDF materials have pages; a Word/Excel "
    "material answers 415. The geometry is not a basis for coordinates here -- the "
    "material viewer has no annotations -- but it is carried for layout."
)
_MATERIAL_PAGE_IMAGE_DESCRIPTION = (
    "One page of a registered material, rasterized by the same pdfium as the answer "
    "pages. Only PDF materials can be rasterized; a Word/Excel material answers 415 "
    "instead of being served as raw bytes (`docs/sidecar-api.md` §7.5)."
)

_IMAGE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"image/png": {"schema": {"type": "string", "format": "binary"}}},
        "description": "The page, rasterized at the requested scale.",
        "headers": {
            "ETag": {
                "description": (
                    "Identifies (document contents, page, scale). Send it back as If-None-Match "
                    "to get a 304 instead of a re-render."
                ),
                "schema": {"type": "string"},
            }
        },
    },
    304: {"description": "The client's If-None-Match matches; the image is unchanged."},
}


def _page_image_etag(source: Path, page_index: int, scale: float) -> str:
    """A strong ETag over ``(document contents, page, scale)`` -- PoC 6's cache
    key.

    The document is identified by a digest of its **bytes**, not by its path or
    mtime: ``POST /tests/{id}/answer-layout`` replaces the stored answer sheet
    in place, and a same-size replacement inside the filesystem's timestamp
    granularity would otherwise keep being served from a stale cache.

    ``scale`` is part of the key because a different scale is a different
    image, never a re-rounding of the same one.
    """
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:_ETAG_DIGEST_CHARS]
    return f'"{digest}-p{page_index}-s{scale}"'


def _if_none_match_hits(request: Request, etag: str) -> bool:
    header = request.headers.get("if-none-match")
    if header is None:
        return False
    candidates = {value.strip() for value in header.split(",")}
    # This router only ever issues strong tags, but a proxy may weaken one, and
    # a weak match is still a match for a GET (RFC 9110 §13.1.2).
    return etag in candidates or f"W/{etag}" in candidates or "*" in candidates


def build_page_image_router(
    session_factory: sessionmaker[Session],
    store: LocalFileStore,
    pdf_engine: PdfEngine,
    *,
    pdfium_lock: threading.Lock | None = None,
) -> APIRouter:
    """Build the router. One `SqlAlchemyUnitOfWork` is opened per request.

    ``pdfium_lock`` must be the *same* lock `api.app.create_app` shares with
    answer intake, profile analysis, criteria extraction and PDF export:
    pypdfium2 is not safe to call from several threads of one process, and
    FastAPI runs these synchronous handlers in its worker threadpool. A private
    one is created when omitted (schema export, unit tests).
    """
    render_lock = pdfium_lock or threading.Lock()
    router = APIRouter(tags=["pages"])

    def _uow() -> Iterator[SqlAlchemyUnitOfWork]:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            yield uow

    uow_dependency = Depends(_uow)

    def _submission_pdf_or_404(uow: SqlAlchemyUnitOfWork, submission_id: str) -> Path:
        if uow.submissions.get(submission_id) is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"submission {submission_id!r} not found"
            )
        path = store.submission_source_pdf_path(submission_id)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source PDF not found on disk")
        return path

    def _answer_layout_pdf_or_404(uow: SqlAlchemyUnitOfWork, test_id: str) -> Path:
        if uow.tests.get(test_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"test {test_id!r} not found")
        path = store.test_answer_layout_pdf_path(test_id)
        if not path.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"test {test_id!r} has no answer sheet uploaded yet",
            )
        return path

    def _material_pdf_or_404(
        uow: SqlAlchemyUnitOfWork, test_id: str, material_id: str
    ) -> Path:
        """The stored file of one registered material, or a 4xx naming why not.

        The row is looked up under its test, so a material id borrowed from
        another test cannot be opened through this one. The path comes from
        `TestMaterial.stored_path` through `LocalFileStore.resolve_stored_path`,
        the same root-escape-checked resolution every other stored path uses.

        A material that is **not a PDF** is refused with 415 before its bytes
        are touched: the viewer can only show rasterized pages, and Issue #207
        removed raw document bytes from the renderer's reach -- so serving the
        file would be a second, undesigned way for a document to leave the
        sidecar. The refusal is explicit rather than an empty page, so the
        window can say the format has no in-app preview.
        """
        if uow.tests.get(test_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"test {test_id!r} not found")
        material = next(
            (
                candidate
                for candidate in uow.test_materials.list_for_test(test_id)
                if candidate.id == material_id
            ),
            None,
        )
        if material is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"material {material_id!r} not found for test {test_id!r}",
            )
        try:
            extension = material_extension(material.stored_path.rsplit("/", 1)[-1])
        except MaterialIntakeError as exc:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="この資料は形式を判別できないためプレビューできません",
            ) from exc
        if extension != "pdf":
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="この形式の資料はアプリ内でプレビューできません",
            )
        path = store.resolve_stored_path(material.stored_path)
        if not path.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="material file not found on disk"
            )
        return path

    def _pages(source: Path) -> DocumentPagesResponse:
        """Read every page's geometry **through `PdfEngine.page_geometry`** --
        the same call `adapters.pdf.pdfium_pypdf_engine` feeds into
        `domain.pdf_geometry` when it transforms an annotation's coordinates.

        Deriving the crop box or the rotation here instead would be a second
        path to the same number, and a second path is where the two can start
        to differ (Issue #207 acceptance condition 2, pinned by
        `test_page_image_api.py::test_geometry_is_the_transforms_own_page_geometry`).
        """
        page_count = pdf_engine.page_count(source)
        return DocumentPagesResponse(
            page_count=page_count,
            pages=[
                PageGeometryResponse.from_geometry(
                    page_index, pdf_engine.page_geometry(source, page_index)
                )
                for page_index in range(page_count)
            ],
        )

    def _page_image(request: Request, source: Path, page_index: int, scale: float) -> Response:
        page_count = pdf_engine.page_count(source)
        if page_index >= page_count:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"page {page_index} is out of range; the document has {page_count} page(s)",
            )
        etag = _page_image_etag(source, page_index, scale)
        headers = {"ETag": etag, "Cache-Control": "no-cache"}
        if _if_none_match_hits(request, etag):
            # Checked *before* rendering: skipping the re-render is what the
            # ETag is for (PoC 6 measured 21 ms/page at scale 2.0).
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
        with render_lock:
            png = pdf_engine.render_page_png(source, page_index, scale=scale)
        return Response(content=png, media_type="image/png", headers=headers)

    @router.get(
        "/submissions/{submission_id}/pages",
        response_model=DocumentPagesResponse,
        description=_LIST_SUBMISSION_PAGES_DESCRIPTION,
    )
    def list_submission_pages(
        submission_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> DocumentPagesResponse:
        return _pages(_submission_pdf_or_404(uow, submission_id))

    @router.get(
        "/submissions/{submission_id}/pages/{page_index}/image",
        # `response_class=Response` (the plain Starlette base, media_type=None)
        # for the same reason as `recognitions_router.get_answer_image`: the
        # route default would also advertise `application/json`, and the Dart
        # generator picks that one first and JSON-decodes the PNG bytes.
        response_class=Response,
        responses=_IMAGE_RESPONSES,
        description=_SUBMISSION_PAGE_IMAGE_DESCRIPTION,
    )
    def get_submission_page_image(
        request: Request,
        submission_id: str,
        page_index: int = PathParam(ge=0, description="0-based page index."),
        scale: PageImageScale = DEFAULT_SCALE,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> Response:
        return _page_image(request, _submission_pdf_or_404(uow, submission_id), page_index, scale)

    @router.get(
        "/tests/{test_id}/answer-layout/pages",
        response_model=DocumentPagesResponse,
        description=_LIST_ANSWER_LAYOUT_PAGES_DESCRIPTION,
    )
    def list_answer_layout_pages(
        test_id: str, uow: SqlAlchemyUnitOfWork = uow_dependency
    ) -> DocumentPagesResponse:
        return _pages(_answer_layout_pdf_or_404(uow, test_id))

    @router.get(
        "/tests/{test_id}/answer-layout/pages/{page_index}/image",
        response_class=Response,
        responses=_IMAGE_RESPONSES,
        description=_ANSWER_LAYOUT_PAGE_IMAGE_DESCRIPTION,
    )
    def get_answer_layout_page_image(
        request: Request,
        test_id: str,
        page_index: int = PathParam(ge=0, description="0-based page index."),
        scale: PageImageScale = DEFAULT_SCALE,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> Response:
        return _page_image(request, _answer_layout_pdf_or_404(uow, test_id), page_index, scale)

    @router.get(
        "/tests/{test_id}/materials/{material_id}/pages",
        response_model=DocumentPagesResponse,
        description=_MATERIAL_PAGES_DESCRIPTION,
    )
    def list_material_pages(
        test_id: str,
        material_id: str,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> DocumentPagesResponse:
        return _pages(_material_pdf_or_404(uow, test_id, material_id))

    @router.get(
        "/tests/{test_id}/materials/{material_id}/pages/{page_index}/image",
        response_class=Response,
        responses=_IMAGE_RESPONSES,
        description=_MATERIAL_PAGE_IMAGE_DESCRIPTION,
    )
    def get_material_page_image(
        request: Request,
        test_id: str,
        material_id: str,
        page_index: int = PathParam(ge=0, description="0-based page index."),
        scale: PageImageScale = DEFAULT_SCALE,
        uow: SqlAlchemyUnitOfWork = uow_dependency,
    ) -> Response:
        return _page_image(
            request, _material_pdf_or_404(uow, test_id, material_id), page_index, scale
        )

    return router
