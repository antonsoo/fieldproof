"""Print the retained actual CLI before/after results as a compact terminal receipt."""

import json
from pathlib import Path

root = Path(__file__).resolve().parent
before = json.loads((root / "before.json").read_text())
after = json.loads((root / "after.json").read_text())

print("Fieldproof CLI report writes - bundled synthetic invoice")
print(f"Source PDF: {after['inputs']['invoice.pdf']['bytes']:,} bytes")
print("\nProtected destination cases              Before          After")
print(
    "Source aliases (document and fixture)    "
    f"{sum(c['exit'] == 0 for c in before['cases'][:15])} overwrites   "
    f"{sum(c['exit'] == 2 for c in after['cases'][:15])} refused"
)
print(
    "Other output symlinks                    "
    f"{sum(not c['target_preserved'] for c in before['cases'][15:17])} changed       "
    f"{sum(c['target_preserved'] for c in after['cases'][15:17])} preserved"
)
print("\n4,096-byte child-process write limit:")
for old, new in zip(before["cases"][-2:], after["cases"][-2:], strict=True):
    print(
        f"  {new['case']:21s} {old['remaining_bytes']:6,d} bytes -> "
        f"{new['remaining_bytes']:6,d} bytes retained"
    )
    print(f"    {new['stderr_tail'][0]}")
print("\nNormal extract / verify-in-place / verify-copy:")
for old, new in zip(before["controls"], after["controls"], strict=True):
    same = old["report_sha256"] == new["report_sha256"]
    print(f"  {new['case']:21s} exit {new['exit']}; identical JSON: {same}; mode {new['mode']}")
print("\nNo API calls. Temporary test copies only. No leftover temporary reports.")
