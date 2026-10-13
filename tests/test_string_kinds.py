"""Field spelling and container names cannot invent a string's semantic kind."""

from io import BytesIO

import pytest
from pydantic import BaseModel, create_model
from reportlab.pdfgen.canvas import Canvas

from fieldproof.document import load_pdf
from fieldproof.extract.base import ExtractionError, validate_data
from fieldproof.schemas import Evidenced, EvidencedDate, EvidencedText
from fieldproof.verify import verify


def document(*lines):
    stream = BytesIO()
    canvas = Canvas(stream, invariant=True)
    for index, line in enumerate(lines):
        canvas.drawString(50, 730 - 25 * index, line)
    canvas.save()
    return load_pdf(stream.getvalue())


def claim(value, quote=None):
    return {"value": value, "evidence": [quote if quote is not None else value]}


@pytest.mark.parametrize(
    "name",
    [
        "candidate_name",
        "candidateName",
        "updated_by",
        "validate_status",
        "consolidated_notes",
    ],
)
def test_unrelated_words_do_not_turn_an_exact_quote_into_an_invalid_date(name):
    schema = create_model("Applicant", **{name: (Evidenced[str], ...)})
    data = schema.model_validate({name: claim("Example Works")})
    (field,) = verify(data, document("Example Works")).fields
    assert field.status == "verified" and field.rects and field.matched_text == "Example Works"
    assert field.reasons == [] and field.notes == []
    assert "declared_kind" not in field.to_dict()


@pytest.mark.parametrize("container", ["model", "list", "mapping"])
def test_only_the_final_named_member_supplies_a_date_hint(container):
    class Name(BaseModel):
        name: Evidenced[str]

    if container == "model":
        annotation, value = Name, {"name": claim("Example Works")}
    elif container == "list":
        annotation, value = list[Name], [{"name": claim("Example Works")}]
    else:
        annotation, value = dict[str, Name], {'x"].issue_date': {"name": claim("Example Works")}}
    schema = create_model("Envelope", date_record=(annotation, ...))
    (field,) = verify(
        schema.model_validate({"date_record": value}), document("Example Works")
    ).fields
    assert field.status == "verified"


@pytest.mark.parametrize(
    "name",
    [
        "date",
        "issue_date",
        "dueDate",
        "dateOfBirth",
        "ISSUE_DATE",
        "birthdate",
        "birthdates",
        "date2",
    ],
)
def test_calendar_validation_remains_strict_for_conventional_leaf_names(name):
    schema = create_model("Dates", **{name: (Evidenced[str], ...)})
    (field,) = verify(
        schema.model_validate({name: claim("2026-02-30")}), document("2026-02-30")
    ).fields
    assert field.status == "needs_review" and "calendar-valid" in field.reasons[0]
    assert field.matched_text == "2026-02-30" and field.rects


def test_sequence_indices_keep_the_date_collection_hint_and_mapping_keys_are_decoded():
    class Form(BaseModel):
        dates: tuple[Evidenced[str], ...]
        fields: dict[str, Evidenced[str]]

    form = Form.model_validate(
        {
            "dates": [claim("2026-02-30")],
            "fields": {"due_date": claim("2026-02-30"), "candidate_name": claim("Example Works")},
        }
    )
    results = verify(form, document("2026-02-30", "Example Works")).fields
    assert [field.status for field in results] == ["needs_review", "needs_review", "verified"]


def test_explicit_kinds_survive_nested_json_roundtrips_without_changing_claims():
    class Form(BaseModel):
        schedule: dict[str, tuple[EvidencedDate, ...]]
        date_label: EvidencedText

    raw = {"schedule": {"candidate[0]": [claim("2026-02-30")]}, "date_label": claim("YYYY-MM-DD")}
    form = validate_data(raw, Form, "form.json")
    assert form.model_dump(mode="json") == {
        **raw,
        "schedule": {
            "candidate[0]": [{**raw["schedule"]["candidate[0]"][0], "page": None}],
        },
        "date_label": {**raw["date_label"], "page": None},
    }
    restored = Form.model_validate_json(form.model_dump_json())
    report = verify(restored, document("2026-02-30", "YYYY-MM-DD"))
    assert [field.status for field in report.fields] == ["needs_review", "verified"]
    assert [field.to_dict()["declared_kind"] for field in report.fields] == ["date", "text"]
    assert report.fields[0].matched_text == "2026-02-30"


def test_an_explicit_date_with_a_nonconventional_name_accepts_written_evidence():
    class Term(BaseModel):
        effective: EvidencedDate

    (field,) = verify(
        Term.model_validate({"effective": claim("2026-05-01", "May 1, 2026")}),
        document("May 1, 2026"),
    ).fields
    assert field.status == "verified" and field.declared_kind == "date"


@pytest.mark.parametrize("kind", [Evidenced[str], EvidencedText, EvidencedDate])
def test_only_text_receives_requested_letter_tolerance(kind):
    schema = create_model("Form", candidate_name=(kind, ...))
    (field,) = verify(
        schema.model_validate(
            {"candidate_name": claim("Internationxl Shipping", "International Shipping")}
        ),
        document("International Shipping"),
        text_edit_tolerance=1,
    ).fields
    if kind is EvidencedDate:
        assert field.status == "needs_review" and "calendar-valid" in field.reasons[0]
        assert not field.notes
    else:
        assert field.status == "verified" and "accepted" in field.notes[0]


def test_conflicting_date_notes_follow_the_actual_check_instead_of_the_path_spelling():
    class Form(BaseModel):
        candidate_name: Evidenced[str]
        effective: EvidencedDate

    report = verify(
        Form.model_validate(
            {
                "candidate_name": claim("Example Workx", "Example Works"),
                "effective": claim("2026-03-04", "03/04/2026"),
            }
        ),
        document("Example Works", "03/04/2026", "31/12/2025", "12/31/2025"),
        default_date_order="dmy",
    )
    text, date = report.fields
    assert text.status == date.status == "needs_review"
    assert not any("date conventions" in reason for reason in text.reasons)
    assert any("date conventions" in reason for reason in date.reasons)


def test_declared_text_remains_an_eligible_row_anchor():
    class Row(BaseModel):
        name: EvidencedText
        amount: Evidenced[float]

    class Form(BaseModel):
        rows: list[Row]

    report = verify(
        Form.model_validate({"rows": [{"name": claim("Alpha"), "amount": claim(10, "10.00")}]}),
        document("Alpha 10.00", "Beta 10.00"),
    )
    assert report.counts == {"verified": 2, "needs_review": 0, "unsupported": 0}
    assert report.fields[0].declared_kind == "text" and report.fields[0].notes == []
    assert "same visual line" in report.fields[1].notes[0]


def test_json_cannot_override_the_schema_kind():
    class Form(BaseModel):
        effective: EvidencedDate

    with pytest.raises(ExtractionError, match="effective.declared_kind: Extra inputs"):
        validate_data(
            {"effective": {**claim("2026-02-30"), "declared_kind": "text"}}, Form, "form.json"
        )


@pytest.mark.parametrize("evidence", [[], ["missing quote"]])
def test_declared_kind_is_retained_even_without_grounding(evidence):
    class Form(BaseModel):
        effective: EvidencedDate

    (field,) = verify(
        Form(effective=EvidencedDate(value="2026-05-01", evidence=evidence)), document("Elsewhere")
    ).fields
    assert field.status == "unsupported" and field.to_dict()["declared_kind"] == "date"
