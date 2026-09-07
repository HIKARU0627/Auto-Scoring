"""Resolving a font the PDF export can really draw with, on machines the
product itself does not target.

Production only looks for the Windows-shipped Japanese fonts
(`pdfium_pypdf_engine._JAPANESE_FONT_CANDIDATES`, Issue #23), which is a
deliberate decision -- bundling and redistributing a font file was the cost
being avoided (docs/pdf-export.md "日本語フォントの解決"). The consequence is
that every test whose export draws text raised `JapaneseFontNotFoundError`
on Linux: 13 of them (Issue #60), on top of the two this was originally
written for in `test_e2e_acceptance.py` (Issue #25). It lives here now that
four modules need it, rather than in four copies.

Nothing here weakens what a test asserts. It appends a fallback *after* the
production candidates, so Windows still resolves the real fonts and never
reaches any of this; and where no installed font can draw what a test checks
for, the test skips with that as its stated reason instead of asserting
something less.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import auto_scoring.adapters.pdf.pdfium_pypdf_engine as engine_module

#: Fonts to try when none of `_JAPANESE_FONT_CANDIDATES` -- the
#: Windows-shipped fonts the product itself uses -- exists.
#:
#: Without this, the text-bearing export tests could only ever run on the
#: windows-latest CI, and a test nobody can run locally is exactly how their
#: assertions came to be `exists()` and `size > 0` in the first place
#: (Issue #25 review, round 1). The list is *appended* to the production
#: candidates, so on Windows the real fonts are still found first and nothing
#: here is ever reached.
#:
#: Which entry gets used depends on the characters a given test actually
#: draws, because coverage here is patchy: `DroidSansFallbackFull` is the
#: only kanji-capable TrueType face on a stock Ubuntu image and it carries no
#: Latin glyphs at all, while `DejaVuSans` is the reverse. (reportlab's
#: `TTFont` also needs TrueType outlines, which rules out the CFF-flavoured
#: Noto CJK OTCs those images do ship.) `install_font_covering` picks per
#: test rather than assuming one font serves both. The first four entries are
#: full-coverage Japanese faces that do serve both, which is why installing
#: one of them removes every skip -- see docs/orca-remote-environment.md
#: section 7.
_FALLBACK_FONTS = (
    Path("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"),
    Path("/usr/share/fonts/truetype/vlgothic/VL-Gothic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf"),
    Path("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"),
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _covers(font_path: Path, required: str) -> bool:
    """Whether reportlab can load ``font_path`` *and* it has a glyph for every
    character in ``required``.

    Existence is not enough, and neither is loadability. A face missing the
    glyphs draws notdef -- literally nothing on the page -- so a test relying
    on it would fail for a reason that has nothing to do with the export
    code. Checked with the same `subfontIndex=0` the engine itself uses.
    """
    try:
        font = TTFont(f"probe-{font_path.stem}", str(font_path), subfontIndex=0)
    except Exception:
        return False
    return all(ord(character) in font.face.charToGlyph for character in required)


def install_font_covering(monkeypatch: pytest.MonkeyPatch, required: str) -> None:
    """Make the export engine resolve a font that can really draw ``required``.

    A no-op on Windows, where the production candidates already cover both
    Japanese and Latin. Elsewhere it appends the first suitable fallback, or
    skips -- an honest "cannot verify on this machine", never a quietly
    weakened assertion.

    ``required`` is the text the caller's *assertions* depend on being drawn,
    not everything its fixture happens to stamp on the page. Demanding more
    than that would skip tests that verify their own subject perfectly well
    (an export's path, hash or idempotency does not care whether the score
    beside the comment came out as glyphs or as notdef).
    """
    original = engine_module._JAPANESE_FONT_CANDIDATES
    if not any(candidate.exists() for candidate in original):
        fallback = next(
            (path for path in _FALLBACK_FONTS if path.exists() and _covers(path, required)),
            None,
        )
        if fallback is None:
            pytest.skip(
                f"no installed TrueType font covers {required!r}; PDF export cannot draw "
                "it on this machine (docs/mvp-acceptance.md section 4)"
            )
        monkeypatch.setattr(engine_module, "_JAPANESE_FONT_CANDIDATES", (*original, fallback))
    # Dropped *after* patching: a resolution made against the old candidate
    # list would otherwise still be handed back (see `forget_registered_font`).
    forget_registered_font()


def forget_registered_font() -> None:
    """Drop the engine's font registration, both caches of it.

    `_ensure_japanese_font_registered` is `lru_cache`d. Clearing that alone is
    not sufficient: reportlab keeps its *own* process-wide registry keyed by
    font name, and silently ignores a second `registerFont` under a name it
    already holds -- so the first face bound to `AutoScoringJPFont` in a
    process stays bound for the rest of it. Tests deliberately need different
    faces on Linux (no single installed font covers both Japanese and Latin
    -- see `_FALLBACK_FONTS`), so without dropping reportlab's entry too,
    whichever test ran first would silently decide the font for every test
    after it, and the rest would assert against glyphs their face does not
    have.

    On Windows this is inert: one font serves every test, and re-registering
    it is what would have happened anyway.
    """
    engine_module._ensure_japanese_font_registered.cache_clear()
    pdfmetrics._fonts.pop(engine_module._JAPANESE_FONT_NAME, None)
