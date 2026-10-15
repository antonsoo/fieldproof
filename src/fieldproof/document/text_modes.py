"""Retain PDF text rendering modes alongside pdfplumber's character geometry.

pdfminer lays out text even when its rendering mode does not paint glyphs.
Keep that text available for review without mistaking it for visible evidence.
"""

from __future__ import annotations

from typing import Any

from pdfminer.layout import LTChar, LTItem, LTPage
from pdfminer.pdfinterp import PDFPageInterpreter, PDFTextState
from pdfplumber.page import Page as PlumberPage
from pdfplumber.page import PdfminerException, PDFPageAggregatorWithMarkedContent


class _ModeAggregator(PDFPageAggregatorWithMarkedContent):
    render_mode: int = 0

    def render_string(
        self, textstate: PDFTextState, seq: Any, ncs: Any, graphicstate: Any
    ) -> None:
        previous = self.render_mode
        self.render_mode = textstate.render
        try:
            super().render_string(textstate, seq, ncs, graphicstate)
        finally:
            self.render_mode = previous

    def render_char(self, *args: Any, **kwargs: Any) -> float:
        advance = super().render_char(*args, **kwargs)
        # Like pdfplumber's marked-content hook, render_char creates one LTChar
        # in the current layout container, including inside Form XObjects.
        char = self.cur_item._objs[-1]
        if isinstance(char, LTChar):
            char.render_mode = self.render_mode  # type: ignore[attr-defined]
        return advance


class ModePage(PlumberPage):
    """The usual pdfplumber page with one additional character attribute."""

    @property
    def layout(self) -> LTPage:
        if hasattr(self, "_layout"):
            return self._layout
        device = _ModeAggregator(
            self.pdf.rsrcmgr, pageno=self.page_number, laparams=self.pdf.laparams
        )
        try:
            PDFPageInterpreter(self.pdf.rsrcmgr, device).process_page(self.page_obj)
        except Exception as exc:
            raise PdfminerException(exc) from exc
        self._layout = device.get_result()
        return self._layout

    def process_object(self, obj: LTItem) -> dict[str, Any]:
        result = super().process_object(obj)
        if isinstance(obj, LTChar):
            result["render_mode"] = obj.render_mode  # type: ignore[attr-defined]
        return result
