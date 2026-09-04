"""Validation rules for an incoming answer PDF, checked before any DB/file write.

Issue #17 acceptance: "不正/暗号化/破損PDFを安全に拒否し、中途半端なDB/fileを残さない"
and "MIME、拡張子、magic bytes、page数、size上限を検証し、path traversalと上書きを防ぐ"
(simplified-design-specification.md §7.1 / business-rules-and-evaluation-data.md §2 (3)).

Pure: everything here operates on bytes/metadata the caller already has. Actually
opening the PDF (page count, encryption) needs pypdf/pdfium and lives in
``adapters`` (``AGENTS.md`` "domain must not import ... any external-service
SDK") -- see :mod:`auto_scoring.domain.pdf_engine`.
"""

from __future__ import annotations

from dataclasses import dataclass


class PdfIntakeError(Exception):
    """An incoming PDF failed validation before any DB/file write happened."""


class PdfInvalidTypeError(PdfIntakeError):
    """Filename, declared content type, or magic bytes don't say "PDF"."""


class PdfTooLargeError(PdfIntakeError):
    """The upload exceeds :attr:`IntakeLimits.max_size_bytes`."""


class PdfEmptyError(PdfIntakeError):
    """The upload has no bytes, or the PDF has no pages."""


class PdfEncryptedError(PdfIntakeError):
    """The PDF requires a password; the sidecar never prompts for one."""


class PdfCorruptedError(PdfIntakeError):
    """The PDF could not be parsed (truncated, malformed, not really a PDF)."""


class PdfPageLimitExceededError(PdfIntakeError):
    """The PDF has more pages than :attr:`IntakeLimits.max_pages` allows."""


_MAGIC = b"%PDF-"
ALLOWED_EXTENSION = ".pdf"
ALLOWED_MIME_TYPES = frozenset({"application/pdf"})


@dataclass(frozen=True, kw_only=True)
class IntakeLimits:
    """Size/page bounds for one uploaded answer PDF. Values are configuration,
    not hardcoded business rules -- callers may tighten or loosen them.
    """

    max_size_bytes: int = 50 * 1024 * 1024
    max_pages: int = 100

    def __post_init__(self) -> None:
        if self.max_size_bytes < 1:
            raise ValueError("max_size_bytes must be positive")
        if self.max_pages < 1:
            raise ValueError("max_pages must be positive")


def validate_filename(filename: str) -> None:
    """Reject empty names, missing/wrong extension, and path traversal.

    Storage never uses the client-supplied filename as a path component (the
    submission id does), but this still rejects a malicious name outright
    rather than silently stripping it, per Issue #17's "path traversalと上書き
    を防ぐ".
    """
    if not filename or not filename.strip():
        raise PdfInvalidTypeError("filename is required")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise PdfInvalidTypeError("filename must not contain path separators")
    if "\x00" in filename:
        raise PdfInvalidTypeError("filename must not contain a null byte")
    stem_and_suffix = filename.rsplit(".", 1)
    if len(stem_and_suffix) != 2 or f".{stem_and_suffix[1].lower()}" != ALLOWED_EXTENSION:
        raise PdfInvalidTypeError(f"filename must end with {ALLOWED_EXTENSION}")


def validate_declared_mime(content_type: str | None) -> None:
    """Reject a declared content type that is present but not ``application/pdf``.

    A missing content type is tolerated -- some upload paths (raw bytes from
    Flutter's file picker) don't set one -- but magic-byte sniffing below still
    catches anything that isn't actually a PDF.
    """
    if content_type is not None and content_type.split(";", 1)[0].strip() not in ALLOWED_MIME_TYPES:
        raise PdfInvalidTypeError(f"unsupported content type: {content_type}")


def sniff_magic_bytes(data: bytes) -> None:
    if not data.startswith(_MAGIC):
        raise PdfInvalidTypeError("file does not start with the PDF signature (%PDF-)")


def validate_size(data: bytes, limits: IntakeLimits) -> None:
    if not data:
        raise PdfEmptyError("uploaded file is empty")
    if len(data) > limits.max_size_bytes:
        raise PdfTooLargeError(f"file size {len(data)} exceeds limit {limits.max_size_bytes}")


def validate_page_count(page_count: int, limits: IntakeLimits) -> None:
    if page_count < 1:
        raise PdfEmptyError("PDF has no pages")
    if page_count > limits.max_pages:
        raise PdfPageLimitExceededError(f"page count {page_count} exceeds limit {limits.max_pages}")


def validate_upload_bytes(
    *,
    filename: str,
    declared_mime: str | None,
    data: bytes,
    limits: IntakeLimits,
) -> None:
    """Everything checkable without opening the PDF: filename, mime, size, magic bytes.

    Call this before touching pypdf/pdfium; :func:`validate_page_count` runs
    once the caller has parsed the file (adapters layer) and knows a real page
    count, and encryption/corruption are surfaced as
    :class:`PdfEncryptedError` / :class:`PdfCorruptedError` from that same
    parse step.
    """
    validate_filename(filename)
    validate_declared_mime(declared_mime)
    validate_size(data, limits)
    sniff_magic_bytes(data)
