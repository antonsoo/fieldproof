"""Retain PDF nonpainting state alongside pdfplumber's character geometry.

pdfminer lays out text even when its rendering mode does not paint glyphs.
Keep that text available for review without mistaking it for visible evidence.
"""

from __future__ import annotations

from copy import copy
from typing import Any

from pdfminer.layout import LTChar, LTItem, LTPage
from pdfminer.pdfinterp import PDFGraphicState, PDFPageInterpreter, PDFStackT, PDFTextState
from pdfminer.pdftypes import dict_value, resolve1, stream_value
from pdfminer.psparser import LIT, literal_name
from pdfminer.utils import Matrix
from pdfplumber.page import Page as PlumberPage
from pdfplumber.page import PdfminerException, PDFPageAggregatorWithMarkedContent


class _PaintState(PDFGraphicState):
    fill_alpha: float = 1.0
    stroke_alpha: float = 1.0
    hidden_group: bool = False

    def copy(self) -> _PaintState:
        # The base class copies only its known attributes, losing our opacity state.
        return copy(self)


class _PaintInterpreter(PDFPageInterpreter):
    graphicstate: _PaintState
    _inherited: _PaintState | None = None
    _inherited_render_mode: int = 0
    _entering_group: bool = False

    def init_state(self, ctm: Matrix) -> None:
        super().init_state(ctm)
        self.graphicstate = self._inherited.copy() if self._inherited is not None else _PaintState()
        self.textstate.render = self._inherited_render_mode

    def dup(self) -> _PaintInterpreter:
        interpreter = super().dup()
        assert isinstance(interpreter, _PaintInterpreter)
        inherited = self.graphicstate.copy()
        if self._entering_group:
            # Transparency groups reset internal alpha to 1. The parent's
            # nonstroking alpha applies when the WHOLE group is composited.
            inherited.hidden_group |= inherited.fill_alpha == 0
            inherited.fill_alpha = inherited.stroke_alpha = 1.0
        interpreter._inherited = inherited
        interpreter._inherited_render_mode = self.textstate.render
        return interpreter

    def do_Do(self, xobjid_arg: PDFStackT) -> None:
        previous = self._entering_group
        xobject = self.xobjmap.get(literal_name(xobjid_arg))
        group = dict_value(stream_value(xobject).get("Group", {})) if xobject is not None else {}
        self._entering_group = group.get("S") is LIT("Transparency")
        try:
            super().do_Do(xobjid_arg)
        finally:
            self._entering_group = previous

    def do_gs(self, name: PDFStackT) -> None:
        super().do_gs(name)
        states = dict_value(self.resources.get("ExtGState", {}))
        state = dict_value(states.get(literal_name(name), {}))
        for key, attribute in (("ca", "fill_alpha"), ("CA", "stroke_alpha")):
            if key in state:
                value = resolve1(state[key])
                # Unsupported/malformed state cannot establish zero opacity.
                # Never infer zero by rounding or multiplying tiny alphas.
                alpha = float(value) if type(value) in (int, float) else 1.0
                setattr(self.graphicstate, attribute, alpha if 0 <= alpha <= 1 else 1.0)


class _ModeAggregator(PDFPageAggregatorWithMarkedContent):
    render_mode: int = 0
    zero_opacity: bool = False

    def render_string(
        self, textstate: PDFTextState, seq: Any, ncs: Any, graphicstate: Any
    ) -> None:
        previous = self.render_mode, self.zero_opacity
        self.render_mode = textstate.render
        mode = textstate.render % 4
        self.zero_opacity = isinstance(graphicstate, _PaintState) and (
            graphicstate.hidden_group
            or (mode == 0 and graphicstate.fill_alpha == 0)
            or (mode == 1 and graphicstate.stroke_alpha == 0)
            or (mode == 2 and graphicstate.fill_alpha == graphicstate.stroke_alpha == 0)
        )
        try:
            super().render_string(textstate, seq, ncs, graphicstate)
        finally:
            self.render_mode, self.zero_opacity = previous

    def render_char(self, *args: Any, **kwargs: Any) -> float:
        advance = super().render_char(*args, **kwargs)
        # Like pdfplumber's marked-content hook, render_char creates one LTChar
        # in the current layout container, including inside Form XObjects.
        char = self.cur_item._objs[-1]
        if isinstance(char, LTChar):
            char.render_mode = self.render_mode  # type: ignore[attr-defined]
            char.zero_opacity = self.zero_opacity  # type: ignore[attr-defined]
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
            _PaintInterpreter(self.pdf.rsrcmgr, device).process_page(self.page_obj)
        except Exception as exc:
            raise PdfminerException(exc) from exc
        self._layout = device.get_result()
        return self._layout

    def process_object(self, obj: LTItem) -> dict[str, Any]:
        result = super().process_object(obj)
        if isinstance(obj, LTChar):
            result["render_mode"] = obj.render_mode  # type: ignore[attr-defined]
            result["zero_opacity"] = obj.zero_opacity  # type: ignore[attr-defined]
        return result
