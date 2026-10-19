"""Saved AcroForm values must survive review rendering and worker transport."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from fieldproof.document.forms import open_render_document
from fieldproof.document.loader import load_pdf
from fieldproof.document.render import render_page_png
from fieldproof.server.app import app
from fieldproof.server.store import store

STUDY = Path(__file__).parents[1] / "studies/form-appearances"


def test_saved_values_and_native_claims_survive_all_authored_form_views(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("form_appearance_replay", STUDY / "replay.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    results = module.replay(tmp_path)["cases"]
    assert len(results) == 14
    for case in results:
        if case["id"] == "xfa-unsupported":
            assert case["render_status"] == case["load_status"] == "rejected"
        elif case["id"] == "form-only":
            assert case["load_status"] == "empty_native_text"
            assert case["review_matches_form_renderer"] is True
        else:
            assert case["review_matches_form_renderer"] is True
            assert case["visible_native_claim"]["status"] == "verified"
            assert case.get("widget_value_in_native_text") in (None, False)
    covered = next(case for case in results if case["id"] == "covered-native-total")
    assert covered["covered_claim"]["status"] == "needs_review"
    for case in results:
        if case["id"] in ("hidden-text", "native-only", "checkbox-unchecked"):
            assert case["form_effect_bbox"] is None
        elif case["id"] != "xfa-unsupported":
            assert case["form_effect_bbox"] is not None


def test_actual_worker_png_keeps_the_filled_value_and_static_form_config() -> None:
    source = (STUDY / "fixtures/filled-text.pdf").read_bytes()
    with open_render_document(source) as pdf:
        assert pdf.formenv is not None
        assert not pdf.formenv.config.m_pJsPlatform
        assert pdf.formenv.config.xfa_disabled
    store._sessions.clear()
    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/documents",
                files={"file": ("filled.pdf", source, "application/pdf")},
            )
            assert upload.status_code == 200, upload.text
            document_id = upload.json()["id"]
            result = client.get(f"/api/documents/{document_id}/pages/1.png")
            assert result.status_code == 200
            with (
                Image.open(io.BytesIO(result.content)) as actual,
                Image.open(io.BytesIO(render_page_png(source, 1))) as expected,
                ImageChops.difference(actual, expected) as delta,
            ):
                assert delta.getbbox() is None
    finally:
        store._sessions.clear()


def test_xfa_is_rejected_at_intake_instead_of_showing_an_incomplete_static_page() -> None:
    source = (STUDY / "fixtures/xfa-unsupported.pdf").read_bytes()
    with pytest.raises(ValueError, match="XFA forms are not supported"):
        load_pdf(source)
    store._sessions.clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/documents", files={"file": ("xfa.pdf", source, "application/pdf")}
            )
            assert response.status_code == 422
            assert "XFA forms are not supported" in response.json()["detail"]
            assert client.get("/api/documents").json()["documents"] == []
    finally:
        store._sessions.clear()
