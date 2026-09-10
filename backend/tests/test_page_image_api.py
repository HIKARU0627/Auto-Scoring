"""HTTP integration tests for `auto_scoring.api.page_image_router` (Issue #207).

These endpoints exist so the Electron UI never renders a PDF itself: the
sidecar rasterizes the page and the UI shows the picture (PoC 6 approach B,
`docs/poc-6-pdf-coordinates.md`). What makes that worth doing is that **one
pdfium defines "the displayed page" for both the picture and the coordinate
transform** -- so the tests that matter here are the ones that would go red if
a second definition appeared:

* `test_geometry_is_the_transforms_own_page_geometry` -- the geometry payload
  is `PdfEngine.page_geometry`'s own values, not a second derivation. Every
  fixture below is chosen so a plausible second derivation (MediaBox instead of
  CropBox, before ``/Rotate`` instead of after) gives a *different* number;
  `test_the_fixture_set_can_tell_a_second_derivation_apart` asserts that, so the
  comparison above cannot pass vacuously.
* `test_image_pixel_size_is_the_displayed_page_times_scale` -- the picture is
  the displayed page scaled, over rotations and CropBox/MediaBox insets. This
  is the property that lets a renderer divide a click position by the image's
  own pixel width and get the same normalized coordinate the sidecar's
  transform would.

Every PDF here is synthesized in-process (`AGENTS.md` "Verification": no real
data).
"""

from __future__ import annotations

import math
import os
import struct
import threading
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.api.page_image_router import ALLOWED_SCALES, DEFAULT_SCALE
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from tests.support import make_submission, make_test

_TOKEN = "page-image-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

_A4 = (595.0, 842.0)


@dataclass(frozen=True)
class _Fixture:
    """One synthetic page shape.

    ``media_origin`` moves the MediaBox off ``(0, 0)`` and ``crop_inset`` cuts
    a CropBox out of it (left, bottom, right, top) -- the two structures PoC 3
    and PoC 6 found to separate a correct implementation from one that reads
    the wrong box.
    """

    name: str
    size: tuple[float, float] = _A4
    rotation: int = 0
    media_origin: tuple[float, float] = (0.0, 0.0)
    crop_inset: tuple[float, float, float, float] | None = None


_FIXTURES = (
    _Fixture("portrait"),
    _Fixture("rotate-90", rotation=90),
    _Fixture("rotate-180", rotation=180),
    _Fixture("rotate-270", rotation=270),
    _Fixture("landscape", size=(_A4[1], _A4[0])),
    _Fixture("media-origin", media_origin=(23.0, 37.0)),
    _Fixture("crop-inset", crop_inset=(20.0, 30.0, 15.0, 40.0)),
    _Fixture(
        "crop-inset-rotated-origin",
        rotation=270,
        media_origin=(23.0, 37.0),
        crop_inset=(20.0, 30.0, 15.0, 40.0),
    ),
)


def _write_pdf(path: Path, fixture: _Fixture, *, pages: int = 1, ink_x: float = 60.0) -> Path:
    """Synthesize ``fixture`` as a real PDF at ``path``.

    ``ink_x`` shifts the drawn rectangle so two otherwise identical documents
    can be told apart by their bytes (the ETag tests).
    """
    width, height = fixture.size
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))
    for _ in range(pages):
        pdf_canvas.setFillColorRGB(0, 0, 0)
        pdf_canvas.rect(ink_x, 80.0, 120.0, 160.0, stroke=0, fill=1)
        pdf_canvas.showPage()
    pdf_canvas.save()

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(buffer.getvalue())))
    origin_x, origin_y = fixture.media_origin
    for page in writer.pages:
        page.mediabox = RectangleObject((origin_x, origin_y, origin_x + width, origin_y + height))
        if fixture.crop_inset is not None:
            left, bottom, right, top = fixture.crop_inset
            page.cropbox = RectangleObject(
                (
                    origin_x + left,
                    origin_y + bottom,
                    origin_x + width - right,
                    origin_y + height - top,
                )
            )
        page.rotation = fixture.rotation
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _png_pixel_size(data: bytes) -> tuple[int, int]:
    """Width and height straight out of the PNG's IHDR chunk."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


class _CountingEngine:
    """`PdfEngine` that records every rasterization, so a test can assert a
    render did *not* happen (the 304 path) rather than only that the response
    looked right."""

    def __init__(self, inner: PdfEngine) -> None:
        self._inner = inner
        self.renders: list[tuple[Path, int, float]] = []

    def page_count(self, source: Path) -> int:
        return self._inner.page_count(source)

    def is_encrypted(self, source: Path) -> bool:
        return self._inner.is_encrypted(source)

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        return self._inner.page_geometry(source, page_index)

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        self.renders.append((source, page_index, scale))
        return self._inner.render_page_png(source, page_index, scale=scale)

    # The two write paths exist only to satisfy `PdfEngine`; this router never
    # writes a PDF.
    def stamp_markers(
        self,
        source: Path,
        destination: Path,
        markers: Mapping[int, Sequence[NormalizedPoint]],
        *,
        mark_size_pt: float = 8.0,
    ) -> None:
        self._inner.stamp_markers(source, destination, markers, mark_size_pt=mark_size_pt)

    def render_annotations(
        self,
        source: Path,
        destination: Path,
        marks: Mapping[int, Sequence[AnnotationMark]],
        note_pages: Sequence[Sequence[AnnotationMark]] = (),
    ) -> None:
        self._inner.render_annotations(source, destination, marks, note_pages)


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def counting_engine() -> _CountingEngine:
    """Named away from conftest's SQLAlchemy ``engine`` fixture."""
    return _CountingEngine(PdfiumPypdfEngine())


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    data_root: Path,
    counting_engine: _CountingEngine,
) -> Iterator[TestClient]:
    app = create_app(
        api_token=_TOKEN,
        session_factory=session_factory,
        data_root=data_root,
        pdf_engine=counting_engine,
        pdfium_lock=threading.Lock(),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def store(data_root: Path) -> LocalFileStore:
    return LocalFileStore(data_root)


def _seed_rows(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.tests.add(make_test())
        uow.submissions.add(make_submission())
        uow.commit()


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> None:
    _seed_rows(session_factory)


def _put_submission_pdf(
    store: LocalFileStore, fixture: _Fixture, *, pages: int = 1, ink_x: float = 60.0
) -> Path:
    return _write_pdf(store.submission_source_pdf_path("sub-1"), fixture, pages=pages, ink_x=ink_x)


def _put_answer_layout_pdf(
    store: LocalFileStore, fixture: _Fixture, *, pages: int = 1, ink_x: float = 60.0
) -> Path:
    return _write_pdf(
        store.test_answer_layout_pdf_path("test-1"), fixture, pages=pages, ink_x=ink_x
    )


# --------------------------------------------------------------------------
# The geometry comes from the transform's own PageGeometry (condition 2)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda fixture: fixture.name)
@pytest.mark.usefixtures("seeded")
def test_geometry_is_the_transforms_own_page_geometry(
    client: TestClient, store: LocalFileStore, fixture: _Fixture
) -> None:
    """Every reported number is `PdfEngine.page_geometry`'s -- the object
    `domain.pdf_geometry` transforms coordinates against.

    A router deriving the size itself (from the MediaBox, or before applying
    ``/Rotate``) would disagree with at least one fixture; see
    `test_the_fixture_set_can_tell_a_second_derivation_apart`.
    """
    source = _put_submission_pdf(store, fixture)
    expected = PdfiumPypdfEngine().page_geometry(source, 0)

    response = client.get("/submissions/sub-1/pages", headers=_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 1
    page = body["pages"][0]
    assert page["page_index"] == 0
    assert page["displayed_width"] == pytest.approx(expected.displayed_width)
    assert page["displayed_height"] == pytest.approx(expected.displayed_height)
    assert page["rotation"] == expected.normalized_rotation


def test_the_fixture_set_can_tell_a_second_derivation_apart(tmp_path: Path) -> None:
    """The fixtures above actually separate `PageGeometry` from the second
    derivations a router could plausibly reach for.

    Without this, a suite of upright A4 pages at the origin would let a router
    read the raw MediaBox and still pass every assertion in this file -- the
    comparisons would be true and empty at the same time.
    """
    geometries = {
        fixture.name: PdfiumPypdfEngine().page_geometry(
            _write_pdf(tmp_path / f"{fixture.name}.pdf", fixture), 0
        )
        for fixture in _FIXTURES
    }

    # A router that never applied /Rotate would report `crop_width` here.
    assert any(geometry.displayed_width != geometry.crop_width for geometry in geometries.values())
    # A router that read the MediaBox would report the full page size here.
    assert any(
        (geometries[fixture.name].crop_width, geometries[fixture.name].crop_height) != fixture.size
        for fixture in _FIXTURES
    )


@pytest.mark.usefixtures("seeded")
def test_geometry_lists_every_page_in_order(client: TestClient, store: LocalFileStore) -> None:
    _put_submission_pdf(store, _FIXTURES[0], pages=3)

    body = client.get("/submissions/sub-1/pages", headers=_AUTH).json()

    assert body["page_count"] == 3
    assert [page["page_index"] for page in body["pages"]] == [0, 1, 2]


@pytest.mark.usefixtures("seeded")
def test_answer_layout_geometry_reads_the_stored_answer_sheet(
    client: TestClient, store: LocalFileStore
) -> None:
    source = _put_answer_layout_pdf(store, _Fixture("rotate-90", rotation=90))
    expected = PdfiumPypdfEngine().page_geometry(source, 0)

    body = client.get("/tests/test-1/answer-layout/pages", headers=_AUTH).json()

    assert body["pages"][0]["displayed_width"] == pytest.approx(expected.displayed_width)
    assert body["pages"][0]["rotation"] == 90


# --------------------------------------------------------------------------
# The image is the displayed page times the scale (condition 1's foundation)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda fixture: fixture.name)
@pytest.mark.parametrize("scale", ALLOWED_SCALES)
@pytest.mark.usefixtures("seeded")
def test_image_pixel_size_is_the_displayed_page_times_scale(
    client: TestClient, store: LocalFileStore, fixture: _Fixture, scale: float
) -> None:
    """pdfium rasterizes into ``ceil(displayed x scale)`` pixels each way.

    This is the whole basis for "divide the click position by the image's own
    pixel width": the picture covers the displayed page exactly, so the two
    normalizations are the same number.
    """
    source = _put_submission_pdf(store, fixture)
    geometry = PdfiumPypdfEngine().page_geometry(source, 0)

    response = client.get(
        "/submissions/sub-1/pages/0/image", params={"scale": scale}, headers=_AUTH
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert _png_pixel_size(response.content) == (
        math.ceil(geometry.displayed_width * scale),
        math.ceil(geometry.displayed_height * scale),
    )


@pytest.mark.usefixtures("seeded")
def test_the_default_scale_is_2(
    client: TestClient, store: LocalFileStore, counting_engine: _CountingEngine
) -> None:
    _put_submission_pdf(store, _FIXTURES[0])

    response = client.get("/submissions/sub-1/pages/0/image", headers=_AUTH)

    assert response.status_code == 200
    assert counting_engine.renders == [
        (store.submission_source_pdf_path("sub-1"), 0, DEFAULT_SCALE)
    ]
    assert DEFAULT_SCALE == 2.0


@pytest.mark.usefixtures("seeded")
def test_the_answer_layout_image_comes_from_the_stored_answer_sheet(
    client: TestClient, store: LocalFileStore
) -> None:
    source = _put_answer_layout_pdf(store, _Fixture("rotate-270", rotation=270))
    geometry = PdfiumPypdfEngine().page_geometry(source, 0)

    response = client.get(
        "/tests/test-1/answer-layout/pages/0/image", params={"scale": 1.0}, headers=_AUTH
    )

    assert response.status_code == 200
    assert _png_pixel_size(response.content) == (
        math.ceil(geometry.displayed_width),
        math.ceil(geometry.displayed_height),
    )


# --------------------------------------------------------------------------
# scale is enumerated server-side and never silently snapped
# --------------------------------------------------------------------------


@pytest.mark.parametrize("scale", ["2.5", "0", "-1", "50", "1.9999", "abc", ""])
@pytest.mark.usefixtures("seeded")
def test_a_scale_outside_the_permitted_set_is_rejected(
    client: TestClient, store: LocalFileStore, counting_engine: _CountingEngine, scale: str
) -> None:
    """Rejected, not rounded to the nearest permitted scale.

    A silently substituted scale hands back an image whose pixel size is not
    the one the caller sized its layout against, and the caller has no way to
    notice -- so the render must not happen at all.
    """
    _put_submission_pdf(store, _FIXTURES[0])

    response = client.get(
        "/submissions/sub-1/pages/0/image", params={"scale": scale}, headers=_AUTH
    )

    assert response.status_code == 422
    assert counting_engine.renders == []


@pytest.mark.usefixtures("seeded")
def test_the_permitted_scales_are_the_documented_three(
    client: TestClient, store: LocalFileStore
) -> None:
    _put_submission_pdf(store, _FIXTURES[0])

    accepted = {
        scale
        for scale in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)
        if client.get(
            "/submissions/sub-1/pages/0/image", params={"scale": scale}, headers=_AUTH
        ).status_code
        == 200
    }

    assert accepted == set(ALLOWED_SCALES)


# --------------------------------------------------------------------------
# ETag: a cache that cannot serve the wrong picture
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
def test_a_matching_if_none_match_skips_the_render(
    client: TestClient, store: LocalFileStore, counting_engine: _CountingEngine
) -> None:
    _put_submission_pdf(store, _FIXTURES[0])
    first = client.get("/submissions/sub-1/pages/0/image", headers=_AUTH)
    etag = first.headers["etag"]
    counting_engine.renders.clear()

    second = client.get(
        "/submissions/sub-1/pages/0/image", headers={**_AUTH, "If-None-Match": etag}
    )

    assert second.status_code == 304
    assert second.headers["etag"] == etag
    assert counting_engine.renders == []


@pytest.mark.usefixtures("seeded")
def test_the_etag_covers_page_and_scale(client: TestClient, store: LocalFileStore) -> None:
    """``(document, page, scale)`` is the cache key PoC 6 measured. A scale
    change is a different image, so it must be a different tag."""
    _put_submission_pdf(store, _FIXTURES[0], pages=2)

    def etag_of(page_index: int, scale: float) -> str:
        response = client.get(
            f"/submissions/sub-1/pages/{page_index}/image",
            params={"scale": scale},
            headers=_AUTH,
        )
        return str(response.headers["etag"])

    tags = {etag_of(0, 1.0), etag_of(0, 2.0), etag_of(1, 1.0), etag_of(1, 2.0)}

    assert len(tags) == 4


@pytest.mark.usefixtures("seeded")
def test_replacing_the_document_invalidates_the_etag(
    client: TestClient, store: LocalFileStore, counting_engine: _CountingEngine
) -> None:
    """``POST /tests/{id}/answer-layout`` overwrites the stored sheet in place.
    The tag is a digest of the bytes, so the replacement cannot be served from
    the old cache entry.

    The replacement's modification time is put back to the original's on
    purpose: that is the case a path+mtime cache key gets wrong, and it is not
    hypothetical -- these two documents differ only in where one rectangle is
    drawn, so they are the same length, and a filesystem whose timestamps are
    coarser than the gap between two writes reports no change at all.
    """
    source = _put_answer_layout_pdf(store, _FIXTURES[0], ink_x=100.0)
    original = source.stat()
    before = client.get("/tests/test-1/answer-layout/pages/0/image", headers=_AUTH)
    _put_answer_layout_pdf(store, _FIXTURES[0], ink_x=300.0)
    assert source.stat().st_size == original.st_size
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    counting_engine.renders.clear()

    after = client.get(
        "/tests/test-1/answer-layout/pages/0/image",
        headers={**_AUTH, "If-None-Match": before.headers["etag"]},
    )

    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]
    assert after.content != before.content
    assert len(counting_engine.renders) == 1


# --------------------------------------------------------------------------
# Missing rows, missing files, pages that do not exist
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/submissions/no-such-submission/pages",
        "/submissions/no-such-submission/pages/0/image",
        "/tests/no-such-test/answer-layout/pages",
        "/tests/no-such-test/answer-layout/pages/0/image",
    ],
)
def test_unknown_document_is_404(client: TestClient, path: str) -> None:
    assert client.get(path, headers=_AUTH).status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/submissions/sub-1/pages",
        "/submissions/sub-1/pages/0/image",
        "/tests/test-1/answer-layout/pages",
        "/tests/test-1/answer-layout/pages/0/image",
    ],
)
@pytest.mark.usefixtures("seeded")
def test_a_row_without_a_stored_file_is_404(client: TestClient, path: str) -> None:
    assert client.get(path, headers=_AUTH).status_code == 404


@pytest.mark.usefixtures("seeded")
def test_a_page_past_the_end_is_404(client: TestClient, store: LocalFileStore) -> None:
    _put_submission_pdf(store, _FIXTURES[0], pages=2)

    assert client.get("/submissions/sub-1/pages/2/image", headers=_AUTH).status_code == 404


@pytest.mark.usefixtures("seeded")
def test_a_negative_page_index_is_rejected(client: TestClient, store: LocalFileStore) -> None:
    _put_submission_pdf(store, _FIXTURES[0])

    assert client.get("/submissions/sub-1/pages/-1/image", headers=_AUTH).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/submissions/sub-1/pages",
        "/submissions/sub-1/pages/0/image",
        "/tests/test-1/answer-layout/pages",
        "/tests/test-1/answer-layout/pages/0/image",
    ],
)
def test_the_page_endpoints_require_the_bearer_token(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 401
