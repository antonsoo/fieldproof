"""Audit correct and deliberately swapped row claims on pinned CORD word annotations.

No model, OCR or image loading: group labels supply the expected association;
the existing study adapter supplies reading order, text and word boxes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    src = args.src.resolve()
    sys.path.insert(0, str(src))
    prior = Path(__file__).resolve().parents[1] / "cord-grounding"
    sys.path.insert(0, str(prior))
    import pyarrow.parquet as pq
    from adapt import RawWord, _build, _quad_box
    from pydantic import BaseModel
    from run import amount_value

    import fieldproof
    from fieldproof.ground.align import find_candidates_in_document
    from fieldproof.schemas import Evidenced
    from fieldproof.verify.engine import verify

    assert Path(fieldproof.__file__).resolve().is_relative_to(src)

    class Item(BaseModel):
        description: Evidenced[str]
        number: Evidenced[float]

    Item.model_rebuild(_types_namespace={"Evidenced": Evidenced})

    class Form(BaseModel):
        items: list[Item]

    Form.model_rebuild(_types_namespace={"Item": Item})
    manifest = json.loads((prior / "manifest.json").read_text())
    observations = []
    counts: Counter = Counter()
    skipped: Counter = Counter()
    documents = 0
    started = perf_counter()
    sources = [f for f in manifest["files"] if f["dataset"] == "cord-v2"]
    for source in sources:
        path = prior / "cache" / source["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(columns=["ground_truth"]):
            for raw in batch.to_pylist():
                gold = json.loads(raw["ground_truth"])
                meta = gold["meta"]
                doc_id = f"cord-{meta['split']}-{meta['image_id']}"
                documents += 1
                words = []
                groups = defaultdict(lambda: defaultdict(list))
                for index, line in enumerate(gold["valid_line"]):
                    key = (line.get("group_id"), line.get("sub_group_id"))
                    groups[key][line["category"]].append(index)
                    for word in line["words"]:
                        words.append(
                            RawWord(
                                word["text"],
                                *_quad_box(word["quad"]),
                                gold_id=index if not word["is_key"] else None,
                            )
                        )
                size = meta["image_size"]
                document, ordered = _build(doc_id, words, size["width"], size["height"])
                page = document.pages[0]
                by_line = defaultdict(list)
                for index, word in enumerate(ordered):
                    if word.gold_id is not None:
                        by_line[word.gold_id].append(index)

                texts = defaultdict(
                    str,
                    {
                        line: " ".join(page.words[i].text for i in indices)
                        for line, indices in by_line.items()
                    },
                )

                eligible = []
                for key, group in groups.items():
                    if key[0] is None or len(group["menu.nm"]) != 1:
                        skipped["group_without_one_name"] += 1
                        continue
                    description = group["menu.nm"][0]
                    for category in ("menu.cnt", "menu.price"):
                        if len(group[category]) != 1:
                            skipped["group_without_one_" + category] += 1
                            continue
                        target = group[category][0]
                        value = amount_value(texts[target])
                        if not texts[description] or value is None:
                            skipped["empty_name_or_unreadable_number"] += 1
                            continue
                        eligible.append((description, target, category, value))

                for description, target, category, true_value in eligible:
                    claims = [("correct", target, true_value)]
                    for other_description, donor, other_category, other_value in eligible:
                        if (
                            other_description != description
                            and other_category == category
                            and other_value != true_value
                        ):
                            claims.append(("swapped", donor, other_value))
                            break
                    for kind, claimed_line, value in claims:
                        quote = texts[claimed_line]
                        repeated = len(find_candidates_in_document(quote, document)) > 1
                        report = verify(
                            Form(
                                items=[
                                    Item(
                                        description=Evidenced(
                                            value=texts[description], evidence=[texts[description]]
                                        ),
                                        number=Evidenced(value=value, evidence=[quote]),
                                    )
                                ]
                            ),
                            document,
                            default_number_style="thousands",
                        )
                        result = report.fields[1]
                        expected_boxes = [page.words[i].bbox.to_dict() for i in by_line[target]]
                        # Judge location against annotated word identities, not
                        # the matcher's scores or its same-row predicate.
                        covered = {
                            i
                            for i, word in enumerate(page.words)
                            if any(
                                rect["x0"] <= word.bbox.x0
                                and rect["x1"] >= word.bbox.x1
                                and rect["top"] <= word.bbox.top
                                and rect["bottom"] >= word.bbox.bottom
                                for rect in result.rects
                            )
                        }
                        located = result.page == 1 and covered == set(by_line[target])
                        outcome = (
                            (
                                "verified_correct"
                                if kind == "correct" and located
                                else "verified_wrong"
                            )
                            if result.status == "verified"
                            else result.status.value
                        )
                        counts[(kind, "repeated" if repeated else "unique", outcome)] += 1
                        observations.append(
                            {
                                "doc": doc_id,
                                "description_line": description,
                                "target_line": target,
                                "claimed_line": claimed_line,
                                "category": category,
                                "kind": kind,
                                "repeated": repeated,
                                "value": value,
                                "quote": quote,
                                "outcome": outcome,
                                "description_status": report.fields[0].status.value,
                                "result": result.to_dict(),
                                "expected_boxes": expected_boxes,
                            }
                        )
    summary = {
        "scope": "CORD annotation replay; scripted claims, not model extraction accuracy.",
        "documents": documents,
        "cases": len(observations),
        "seconds": perf_counter() - started,
        "skipped": dict(skipped),
        "sources": sources,
        "source_sha256": {
            str(path.relative_to(src)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((src / "fieldproof").rglob("*.py"))
        },
        "counts": [
            {"kind": k, "quote": q, "outcome": o, "n": n} for (k, q, o), n in sorted(counts.items())
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "rows.jsonl"
    rows_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in observations))
    summary["rows_sha256"] = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
