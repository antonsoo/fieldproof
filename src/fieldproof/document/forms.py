"""Open a static PDF view with saved AcroForm appearances included."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

import pypdfium2 as pdfium
from pypdfium2 import raw


class UnsupportedPdfFormError(ValueError):
    """A PDF form needs a runtime outside the supported static view."""


@contextmanager
def open_render_document(source: str | Path | bytes) -> Iterator[pdfium.PdfDocument]:
    """Initialize form rendering before any page handles are acquired.

    PDFium's page renderer alone leaves widget values blank. Keep the form
    environment alive until its pages close, including disposable paint-audit
    references. This is a static view: no JavaScript platform or XFA runtime.
    """
    with closing(pdfium.PdfDocument(source)) as pdf:
        if pdf.get_formtype() in (raw.FORMTYPE_XFA_FULL, raw.FORMTYPE_XFA_FOREGROUND):
            raise UnsupportedPdfFormError(
                "XFA forms are not supported; save a static PDF from a form viewer before loading"
            )
        # An explicit null m_pJsPlatform prevents JavaScript even in V8 builds.
        # Do not use init_forms()'s default config, which can enable XFA.
        pdf.init_forms(config=raw.FPDF_FORMFILLINFO(version=2, xfa_disabled=True))
        yield pdf
