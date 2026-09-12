"""HTTP integration tests for material pages (Issue #415).

A registered material is shown in its own window by rasterizing it with the
same pdfium the answer pages use (`api.page_image_router`), so the tests here
are about the two properties that make "open the material" answerable at all:

* the pages come from `TestMaterial.stored_path` through the store's
  root-escape-checked resolution, and from **the test the caller named** --
  a material id borrowed from another test must not open through this one;
* a material that is not a PDF is refused with 415 rather than served as
  bytes, because the renderer has no way to display Word/Excel and Issue #207
  removed raw document bytes from its reach.

Every PDF here is synthesized in-process (`AGENTS.md` "Verification": no real
data).
"""

from __future__ import annotations

import hashlib
import math
import struct
import threading
from collections.abc import Iterator, Mapping, Sequence
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.pdf.pdfium_pypdf_engine import PdfiumPypdfEngine
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.api.page_image_router import ALLOWED_SCALES
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.pdf_engine import AnnotationMark, PdfEngine
from auto_scoring.domain.pdf_geometry import NormalizedPoint, PageGeometry
from auto_scoring.domain.test_material import TestMaterial as MaterialRecord
from tests.support import at, make_test

_TOKEN = "material-page-test-token"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}

_PDF_MATERIAL_ID = "material-pdf"
_DOCX_MATERIAL_ID = "material-docx"


class _CountingEngine:
    """`PdfEngine` that records every rasterization, so the 304 path can be
    asserted as "no render happened" rather than only "the response looked
    right"."""

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


def _write_pdf(path: Path, *, pages: int = 1) -> Path:
    buffer = BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(595.0, 842.0))
    for _ in range(pages):
        pdf_canvas.setFillColorRGB(0, 0, 0)
        pdf_canvas.rect(60.0, 80.0, 120.0, 160.0, stroke=0, fill=1)
        pdf_canvas.showPage()
    pdf_canvas.save()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    return path


def _png_pixel_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _material(
    material_id: str,
    stored_path: str,
    *,
    role: MaterialRole = MaterialRole.ANNOTATION_SAMPLE,
    test_id: str = "test-1",
    size_bytes: int = 1,
) -> MaterialRecord:
    return MaterialRecord(
        id=material_id,
        test_id=test_id,
        role=role,
        stored_path=stored_path,
        sha256=hashlib.sha256(stored_path.encode()).hexdigest(),
        size_bytes=size_bytes,
        original_filename=None,
        created_at=at(),
    )


def _seed(
    session_factory: sessionmaker[Session],
    *,
    materials: Sequence[MaterialRecord] = (),
    test_ids: Sequence[str] = ("test-1",),
) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        for test_id in test_ids:
            if uow.tests.get(test_id) is None:
                uow.tests.add(make_test(id=test_id))
        for material in materials:
            uow.test_materials.add(material)
        uow.commit()


def _put_pdf_material(store: LocalFileStore, *, pages: int = 1) -> str:
    path = store.test_material_path("test-1", _PDF_MATERIAL_ID, "pdf")
    _write_pdf(path, pages=pages)
    return store.relative_path(path)


def _put_docx_material(store: LocalFileStore) -> str:
    path = store.test_material_path("test-1", _DOCX_MATERIAL_ID, "docx")
    path.parent.mkdir(parents=True, exist_ok=True)
    # A ZIP signature is what `domain.material_intake` accepts for `.docx`; the
    # bytes are never parsed because the endpoint refuses before reading them.
    path.write_bytes(b"PK\x03\x04" + b"not a document body")
    return store.relative_path(path)


# --------------------------------------------------------------------------
# PDF material pages come from the stored file and the named test
# --------------------------------------------------------------------------


def test_material_pages_list_every_page_in_order(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, _put_pdf_material(store, pages=3))])

    response = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages", headers=_AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page_count"] == 3
    assert [page["page_index"] for page in body["pages"]] == [0, 1, 2]


def test_material_geometry_is_the_engines_own_page_geometry(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    stored_path = _put_pdf_material(store)
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, stored_path)])
    expected = PdfiumPypdfEngine().page_geometry(store.resolve_stored_path(stored_path), 0)

    body = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages", headers=_AUTH
    ).json()

    page = body["pages"][0]
    assert page["displayed_width"] == pytest.approx(expected.displayed_width)
    assert page["displayed_height"] == pytest.approx(expected.displayed_height)
    assert page["rotation"] == expected.normalized_rotation


@pytest.mark.parametrize("scale", ALLOWED_SCALES)
def test_material_image_pixel_size_is_the_displayed_page_times_scale(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    scale: float,
) -> None:
    stored_path = _put_pdf_material(store)
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, stored_path)])
    geometry = PdfiumPypdfEngine().page_geometry(store.resolve_stored_path(stored_path), 0)

    response = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/0/image",
        params={"scale": scale},
        headers=_AUTH,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert _png_pixel_size(response.content) == (
        math.ceil(geometry.displayed_width * scale),
        math.ceil(geometry.displayed_height * scale),
    )


def test_material_page_renders_through_the_shared_engine_and_default_scale(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    counting_engine: _CountingEngine,
) -> None:
    stored_path = _put_pdf_material(store)
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, stored_path)])

    response = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/0/image", headers=_AUTH
    )

    assert response.status_code == 200
    # The literal 2.0, not the module constant: asserting `DEFAULT_SCALE` would
    # pass for any value it was changed to, so it could not catch a scale
    # change at all.
    assert counting_engine.renders == [
        (store.resolve_stored_path(stored_path), 0, 2.0)
    ]


def test_a_material_from_another_test_is_not_opened_through_this_one(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    path = store.test_material_path("test-2", _PDF_MATERIAL_ID, "pdf")
    _write_pdf(path)
    _seed(
        session_factory,
        materials=[_material(_PDF_MATERIAL_ID, store.relative_path(path), test_id="test-2")],
        test_ids=("test-1", "test-2"),
    )

    response = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages", headers=_AUTH
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------
# Non-PDF materials are refused, not served as bytes
# --------------------------------------------------------------------------


def test_a_non_pdf_material_is_415_and_sends_no_document_bytes(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    stored_path = _put_docx_material(store)
    _seed(
        session_factory,
        materials=[
            _material(
                _DOCX_MATERIAL_ID,
                stored_path,
                role=MaterialRole.ANNOTATION_RESOURCE,
            )
        ],
    )

    pages = client.get(
        f"/tests/test-1/materials/{_DOCX_MATERIAL_ID}/pages", headers=_AUTH
    )
    image = client.get(
        f"/tests/test-1/materials/{_DOCX_MATERIAL_ID}/pages/0/image", headers=_AUTH
    )

    assert pages.status_code == 415
    assert image.status_code == 415
    # The refusal must not carry the stored file: a raw document through the
    # renderer is exactly what Issue #207 removed.
    assert b"PK\x03\x04" not in image.content


# --------------------------------------------------------------------------
# Missing rows, missing files, pages out of range
# --------------------------------------------------------------------------


def test_unknown_material_is_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    # The test must exist, or this would pass on the test-not-found guard and
    # never exercise "this test has no such material".
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, "tests/test-1/materials/x.pdf")])

    assert (
        client.get("/tests/test-1/materials/no-such-material/pages", headers=_AUTH).status_code
        == 404
    )


def test_unknown_test_is_404(client: TestClient) -> None:
    assert (
        client.get("/tests/no-such-test/materials/material-1/pages", headers=_AUTH).status_code
        == 404
    )


def test_a_material_row_without_a_stored_file_is_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, "tests/test-1/materials/x.pdf")])

    assert (
        client.get(
            f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages", headers=_AUTH
        ).status_code
        == 404
    )


def test_a_page_past_the_end_is_404(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, _put_pdf_material(store, pages=2))])

    assert (
        client.get(
            f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/2/image", headers=_AUTH
        ).status_code
        == 404
    )


def test_a_negative_page_index_is_rejected(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
) -> None:
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, _put_pdf_material(store))])

    assert (
        client.get(
            f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/-1/image", headers=_AUTH
        ).status_code
        == 422
    )


# --------------------------------------------------------------------------
# Caching and auth
# --------------------------------------------------------------------------


def test_a_matching_if_none_match_skips_the_render(
    client: TestClient,
    store: LocalFileStore,
    session_factory: sessionmaker[Session],
    counting_engine: _CountingEngine,
) -> None:
    _seed(session_factory, materials=[_material(_PDF_MATERIAL_ID, _put_pdf_material(store))])
    first = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/0/image", headers=_AUTH
    )
    etag = first.headers["etag"]
    counting_engine.renders.clear()

    second = client.get(
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/0/image",
        headers={**_AUTH, "If-None-Match": etag},
    )

    assert second.status_code == 304
    assert counting_engine.renders == []


@pytest.mark.parametrize(
    "path",
    [
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages",
        f"/tests/test-1/materials/{_PDF_MATERIAL_ID}/pages/0/image",
    ],
)
def test_the_material_page_endpoints_require_the_bearer_token(
    client: TestClient, path: str
) -> None:
    assert client.get(path).status_code == 401
