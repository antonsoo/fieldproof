"""Retain PDF nonpainting state alongside pdfplumber's character geometry.

pdfminer lays out text even when its rendering mode does not paint glyphs.
Keep that text available for review without mistaking it for visible evidence.
"""

from __future__ import annotations

import math
from copy import copy
from typing import Any

from pdfminer.layout import LTChar, LTItem, LTPage
from pdfminer.pdfinterp import PDFGraphicState, PDFPageInterpreter, PDFStackT, PDFTextState
from pdfminer.pdftypes import dict_value, resolve1, stream_value
from pdfminer.psparser import LIT, literal_name
from pdfminer.utils import Matrix, Rect
from pdfplumber.page import Page as PlumberPage
from pdfplumber.page import PdfminerException, PDFPageAggregatorWithMarkedContent

from fieldproof.document.clip_bounds import ClipPath, crosses_clip, intersect, transformed_rect


class _PaintState(PDFGraphicState):
    fill_alpha: float = 1.0
    stroke_alpha: float = 1.0
    hidden_group: bool = False
    clip_bounds: Rect | None = None

    def copy(self) -> _PaintState:
        # The base class copies only its known attributes, losing our opacity state.
        return copy(self)


class _PaintInterpreter(PDFPageInterpreter):
    graphicstate: _PaintState
    _inherited: _PaintState | None = None
    _inherited_render_mode: int = 0
    _entering_group: bool = False
    _invoked_bbox: Any = None
    _inherited_bbox: Any = None

    def init_state(self, ctm: Matrix) -> None:
        super().init_state(ctm)
        self.graphicstate = self._inherited.copy() if self._inherited is not None else _PaintState()
        self.textstate.render = self._inherited_render_mode
        self._clip_path = ClipPath()
        # A Form's BBox clips its content, in addition to the invoking clip.
        bounds = transformed_rect(self._inherited_bbox, ctm)
        if bounds is not None:
            self.graphicstate.clip_bounds = intersect(self.graphicstate.clip_bounds, bounds)

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
        interpreter._inherited_bbox = self._invoked_bbox
        return interpreter

    def do_Do(self, xobjid_arg: PDFStackT) -> None:
        previous = self._entering_group, self._invoked_bbox
        xobject = self.xobjmap.get(literal_name(xobjid_arg))
        form = stream_value(xobject) if xobject is not None else None
        group = dict_value(form.get("Group", {})) if form is not None else {}
        self._invoked_bbox = resolve1(form.get("BBox")) if form is not None else None
        self._entering_group = group.get("S") is LIT("Transparency")
        try:
            super().do_Do(xobjid_arg)
        finally:
            self._entering_group, self._invoked_bbox = previous

    # pdfminer's operator dispatch reads each method's positional arity.
    # Keep explicit signatures rather than wrapping these with *args.
    def do_m(self, x: PDFStackT, y: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_m(x, y)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_l(self, x: PDFStackT, y: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_l(x, y)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_c(self, x1: PDFStackT, y1: PDFStackT, x2: PDFStackT,
             y2: PDFStackT, x3: PDFStackT, y3: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_c(x1, y1, x2, y2, x3, y3)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_v(self, x2: PDFStackT, y2: PDFStackT, x3: PDFStackT, y3: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_v(x2, y2, x3, y3)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_y(self, x1: PDFStackT, y1: PDFStackT, x3: PDFStackT, y3: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_y(x1, y1, x3, y3)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_re(self, x: PDFStackT, y: PDFStackT, w: PDFStackT, h: PDFStackT) -> None:
        start = len(self.curpath)
        super().do_re(x, y, w, h)
        self._clip_path.record(self.curpath[start:], self.ctm)

    def do_W(self) -> None:
        self._clip_path.pending = True

    def do_W_a(self) -> None:
        self._clip_path.pending = True

    def do_n(self) -> None:
        super().do_n()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_S(self) -> None:
        super().do_S()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_f(self) -> None:
        super().do_f()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_F(self) -> None:
        self.do_f()

    def do_f_a(self) -> None:
        super().do_f_a()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_B(self) -> None:
        super().do_B()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_B_a(self) -> None:
        super().do_B_a()
        self.graphicstate.clip_bounds = self._clip_path.finish(self.graphicstate.clip_bounds)

    def do_gs(self, name: PDFStackT) -> None:
        super().do_gs(name)
        states = dict_value(self.resources.get("ExtGState", {}))
        state = dict_value(states.get(literal_name(name), {}))
        if "ML" in state and isinstance(self.device, _ModeAggregator):
            self.device.record_miter_limit(resolve1(state["ML"]))
        for key, attribute in (("ca", "fill_alpha"), ("CA", "stroke_alpha")):
            if key in state:
                value = resolve1(state[key])
                # Unsupported/malformed state cannot establish zero opacity.
                # Never infer zero by rounding or multiplying tiny alphas.
                alpha = float(value) if type(value) in (int, float) else 1.0
                setattr(self.graphicstate, attribute, alpha if 0 <= alpha <= 1 else 1.0)

    def do_M(self, miterlimit: PDFStackT) -> None:
        super().do_M(miterlimit)
        if isinstance(self.device, _ModeAggregator):
            self.device.record_miter_limit(miterlimit)


class _ModeAggregator(PDFPageAggregatorWithMarkedContent):
    render_mode: int = 0
    zero_opacity: bool = False
    clip_bounds: Rect | None = None
    miter_limit_bound: float | None = 10.0  # PDF's initial graphics-state value.

    def record_miter_limit(self, value: Any) -> None:
        # Keep an upper bound across the page and every invoked Form. A bad
        # declaration cannot establish a limit, even if a later one is valid.
        if self.miter_limit_bound is None:
            return
        try:
            limit = float(value) if type(value) in (int, float) else math.nan
        except OverflowError:
            limit = math.nan
        self.miter_limit_bound = (
            max(self.miter_limit_bound, limit) if math.isfinite(limit) and limit >= 1 else None
        )

    def render_string(
        self, textstate: PDFTextState, seq: Any, ncs: Any, graphicstate: Any
    ) -> None:
        previous = self.render_mode, self.zero_opacity, self.clip_bounds
        self.clip_bounds = (
            graphicstate.clip_bounds if isinstance(graphicstate, _PaintState) else None
        )
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
            self.render_mode, self.zero_opacity, self.clip_bounds = previous

    def render_char(self, *args: Any, **kwargs: Any) -> float:
        advance = super().render_char(*args, **kwargs)
        # Like pdfplumber's marked-content hook, render_char creates one LTChar
        # in the current layout container, including inside Form XObjects.
        char = self.cur_item._objs[-1]
        if isinstance(char, LTChar):
            char.render_mode = self.render_mode  # type: ignore[attr-defined]
            char.zero_opacity = self.zero_opacity  # type: ignore[attr-defined]
            char.clip_risk = crosses_clip(char.bbox, self.clip_bounds)  # type: ignore[attr-defined]
        return advance


class ModePage(PlumberPage):
    """The usual pdfplumber page with native painting metadata on characters."""

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
        self._miter_limit_bound = device.miter_limit_bound
        return self._layout

    @property
    def miter_limit_bound(self) -> float | None:
        _ = self.layout
        return self._miter_limit_bound

    def process_object(self, obj: LTItem) -> dict[str, Any]:
        result = super().process_object(obj)
        if isinstance(obj, LTChar):
            result["render_mode"] = obj.render_mode  # type: ignore[attr-defined]
            result["zero_opacity"] = obj.zero_opacity  # type: ignore[attr-defined]
            result["clip_risk"] = obj.clip_risk  # type: ignore[attr-defined]
        return result
