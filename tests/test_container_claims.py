"""Declared claims must not disappear or borrow authority through their path labels."""

from io import BytesIO

import pytest
from pydantic import BaseModel, create_model
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document import load_pdf
from fieldproof.schemas import Evidenced, iter_evidenced_fields
from fieldproof.verify import verify


def document():
    stream = BytesIO()
    canvas = Canvas(stream, invariant=True)
    for y, text in [(700, "Alpha 10.00"), (650, "Beta 10.00"), (600, "Example Works")]:
        canvas.drawString(50, y, text)
    canvas.save()
    return load_pdf(stream.getvalue())


@pytest.mark.parametrize("container", ["mapping", "tuple", "nested"])
def test_declared_containers_retain_supported_and_unsupported_claims(container):
    supported = Evidenced[str](value="Example Works", evidence=["Example Works"])
    unsupported = Evidenced[str](value="UNSUPPORTED BANK ACCOUNT")
    if container == "mapping":
        annotation = dict[str, Evidenced[str]]
        value = {"vendor": supported, "bank_account": unsupported}
        expected = ['claims["vendor"]', 'claims["bank_account"]']
    elif container == "tuple":
        annotation = tuple[Evidenced[str], Evidenced[str]]
        value = (supported, unsupported)
        expected = ["claims[0]", "claims[1]"]
    else:
        annotation = dict[str, list[tuple[Evidenced[str], Evidenced[str]]]]
        value = {"a.b[0]": [(supported, unsupported)]}
        expected = ['claims["a.b[0]"][0][0]', 'claims["a.b[0]"][0][1]']
    schema = create_model("Custom", claims=(annotation, ...))
    data = schema(claims=value)
    report = verify(data, document())
    assert [field.path for field in report.fields] == expected
    assert report.counts == {"verified": 1, "needs_review": 0, "unsupported": 1}
    assert report.fields[0].rects and report.fields[0].matched_text == "Example Works"
    assert report.fields[1].reasons == ["no evidence quote was provided for this value"]


def test_a_punctuated_model_name_cannot_overwrite_a_nested_claim():
    class Child(BaseModel):
        b: Evidenced[str]

    schema = create_model("Custom", **{"a.b": (Evidenced[str], ...), "a": (Child, ...)})
    data = schema.model_validate({
        "a.b": {"value": "UNSUPPORTED"},
        "a": {"b": {"value": "Example Works", "evidence": ["Example Works"]}},
    })
    report = verify(data, document())
    assert [field.path for field in report.fields] == ['["a.b"]', "a.b"]
    assert report.counts == {"verified": 1, "needs_review": 0, "unsupported": 1}


def test_distinct_mapping_keys_stay_distinct_and_json_serializable():
    class Form(BaseModel):
        claims: dict[str, Evidenced[str]]

    keys = ["", "0", "a.b", "a[0]", 'a"b', "a\\b", "a\nb", "\u65e5\u672c"]
    form = Form(claims={key: Evidenced[str](value=key) for key in keys})
    fields = list(iter_evidenced_fields(form))
    assert len({path for path, _ in fields}) == len(keys)
    assert [field.value for _, field in fields] == keys
    assert [path for path, _ in fields][:4] == [
        'claims[""]', 'claims["0"]', 'claims["a.b"]', 'claims["a[0]"]',
    ]
    assert "\n" not in "".join(path for path, _ in fields)


@pytest.mark.parametrize("prefix", ["items[0]", 'x"].items[0]', "x\\items[0]"])
def test_mapping_key_text_does_not_create_a_row_hint(prefix):
    class Form(BaseModel):
        claims: dict[str, Evidenced[str | float]]

    form = Form(claims={
        f"{prefix}.name": {"value": "Alpha", "evidence": ["Alpha"]},
        f"{prefix}.amount": {"value": 10.0, "evidence": ["10.00"]},
    })
    report = verify(form, document())
    assert [field.status for field in report.fields] == ["verified", "needs_review"]
    assert "ambiguous" in report.fields[1].reasons[0]
    assert report.fields[1].rects == []


def test_real_sequence_positions_keep_their_row_hint_inside_a_mapping():
    class Row(BaseModel):
        name: Evidenced[str]
        amount: Evidenced[float]

    class Form(BaseModel):
        groups: dict[str, list[Row]]

    form = Form(groups={
        'x"].items[9]': [Row(
            name=Evidenced[str](value="Alpha", evidence=["Alpha"]),
            amount=Evidenced[float](value=10, evidence=["10.00"]),
        )],
    })
    report = verify(form, document())
    assert [field.status for field in report.fields] == ["verified", "verified"]
    assert report.fields[1].notes and "same visual line" in report.fields[1].notes[0]
    assert report.fields[1].rects


def test_non_string_mapping_keys_fail_explicitly_instead_of_hiding_claims():
    class Form(BaseModel):
        claims: dict[int, Evidenced[str]]

    with pytest.raises(ValueError, match="mapping at 'claims' must use string keys, not int"):
        verify(Form(claims={1: Evidenced[str](value="UNSUPPORTED")}), document())
