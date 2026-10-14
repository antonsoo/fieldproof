"""Check actual Calc reads against the scalar fixtures and API capture rows."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calc", type=Path, required=True)
    for phase in ("before", "after"):
        for writer in ("python", "browser"):
            parser.add_argument(f"--{phase}-{writer}", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cases = {item["id"]: item for item in json.loads((Path(__file__).parent / "cases.json").read_text())}
    calc = json.loads(args.calc.read_text())
    captures = {}
    for phase in ("before", "after"):
        for writer in ("python", "browser"):
            path = getattr(args, f"{phase}_{writer}")
            captures[path.parent.name] = (phase, writer, json.loads(path.read_text()))

    records = []
    for book in calc["results"]:
        path = Path(book["file"])
        phase, writer, capture = captures[path.parent.name]
        for row in book["rows"][1:]:
            if path.name == "writer-all.xlsx":
                case = cases[row[0]["text"]]
                source = next(item for item in capture["records"] if item["case"] == case["id"] and item.get("kind", "writer") == "writer")
                original = None
            else:
                if row[0]["text"] != "total":
                    continue
                source = next(item for item in capture["records"] if item.get("file") == path.name)
                case = cases[source["case"]]
                original = source["row"]["original_value"]
            kind = case["cell"]
            value = int(case["integer"]) if "integer" in case else 10**case["powerPlusOne"] + 1 if "powerPlusOne" in case else case["value"]
            expected_type = {"inlineStr": "TEXT", "n": "VALUE", "b": "FORMULA", "blank": "EMPTY"}[kind]
            target = row[1]
            passed = target["type"] == expected_type and (
                target["text"] == source["sourceSpelling"] if kind == "inlineStr"
                else target["number"] == value if kind in ("n", "b") else True
            )
            original_matches = (row[2] == target if original is None
                                else row[2]["type"] == "VALUE" and row[2]["number"] == original)
            passed = passed and original_matches
            numeric_changed = isinstance(value, int) and not isinstance(value, bool) and target["type"] == "VALUE" and target["number"] != value
            records.append({"phase": phase, "writer": writer, "file": book["file"],
                            "case": case["id"], "sourceSpelling": source["sourceSpelling"],
                            "expectedType": expected_type, "agrees": passed,
                            "numericValueChanged": numeric_changed, "value": target,
                            "originalValue": row[2], "originalMatches": original_matches})

    result = {"engine": calc["version"], "workbooks": len(calc["results"]), "observations": len(records),
              "beforeDisagreements": sum(not row["agrees"] for row in records if row["phase"] == "before"),
              "afterDisagreements": sum(not row["agrees"] for row in records if row["phase"] == "after"),
              "beforeChangedIntegerCases": sorted({row["case"] for row in records if row["numericValueChanged"]}),
              "scope": "Actual offline Calc reads. Boolean cells are internally represented as TRUE()/FALSE() formulas by Calc; source workbooks contain typed boolean cells and no formulas. Baseline writer exception is captured separately.",
              "records": records}
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("engine", "workbooks", "observations", "beforeDisagreements", "afterDisagreements", "beforeChangedIntegerCases")}, indent=2))
    assert result["afterDisagreements"] == 0


if __name__ == "__main__":
    main()
