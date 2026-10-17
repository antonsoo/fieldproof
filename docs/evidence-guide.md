# Evidence guide

Each linked study identifies its input, source revision, method and remaining
limits. Counts in an older receipt describe that revision. Source corrections,
installed distributions, hosted static bytes and registry releases are separate
publication stages. For setup, return to the [README](../README.md).

## Grounding and claimed values

| Question | Retained study |
| --- | --- |
| How do strict rules behave on actual receipt OCR and known fields? | [CORD/SROIE receipt audit](../studies/cord-grounding/README.md) |
| Can a sign, rate or digit disappear during numeric comparison? | [Numeric evidence](../studies/numeric-evidence/README.md) |
| Which document conventions can settle an ambiguous number or date? | [Mixed conventions](../studies/mixed-conventions/README.md), [date hints](../studies/date-conventions/README.md) |
| Are date claims and written-date evidence complete? | [Date claims](../studies/date-claims/README.md), [written dates](../studies/written-dates/README.md) |
| Can prose establish a boolean answer? | [Boolean evidence](../studies/boolean-evidence/README.md) |
| Are text kinds, container values and scalar types kept distinct? | [String kinds](../studies/string-kinds/README.md), [container claims](../studies/container-claims/README.md), [claim types](../studies/claim-types/README.md) |
| Can contradictory JSON members or unknown claims disappear? | [Claim integrity](../studies/claim-integrity/README.md) |

## Source locations and relationships

| Question | Retained study |
| --- | --- |
| Does a quoted number belong to this item? | [Row association](../studies/row-association/README.md), [row locality](../studies/row-locality/README.md) |
| Can labelled columns expose a quantity/price swap? | [Column evidence](../studies/column-evidence/README.md) |
| Can printed values disagree arithmetically? | [Arithmetic operands and checks](../studies/arithmetic-evidence/README.md) |
| Does Unicode normalization preserve every candidate's original offsets? | [Unicode grounding](../studies/unicode-grounding/README.md) |
| Can reusable grounding retain complete reports while reducing repeated work? | [Grounding reuse](../studies/grounding-reuse/README.md) |

## Native PDF paint

| Question | Retained study |
| --- | --- |
| Can invisible or clipping-only text verify a claim? | [Rendering modes](../studies/unpainted-text/README.md) |
| What if a painting channel or enclosing group has zero opacity? | [Zero opacity](../studies/zero-opacity/README.md) |
| Do source boxes cross known outer clipping bounds? | [Clipped text](../studies/clipped-text/README.md) |
| Does native text contribute to the displayed raster? | [Native-paint reference](../studies/flat-raster/README.md) |
| Can a replacement one's ink verify the covered original nine? | [Overlapping text](../studies/overlapping-text/README.md) |
| What about italic overhangs, transformed strokes and miter corners? | [Native glyph bounds](../studies/native-glyph-bounds/README.md) |

These are bounded observations. Authored visibility controls are labelled
synthetic and retain conservative visible-text reviews. They do not establish
document authenticity or production error prevalence.

## Review, files and OCR

| Question | Retained study |
| --- | --- |
| Can a CLI report overwrite its source or lose a prior report on write failure? | [Report files](../studies/report-files/README.md) |
| Can review decisions survive session removal and server restart? | [Review archives](../studies/review-archives/README.md) |
| Are spreadsheet identifiers, text and numeric precision preserved? | [Spreadsheet exports](../studies/spreadsheet-export/README.md), [numeric cells](../studies/numeric-xlsx/README.md) |
| Does image-only fallback use actual local recognition? | [OCR fallback](../studies/ocr-fallback/README.md) |
| Can native and scanned pages retain distinct provenance? | [Mixed-page OCR](../studies/mixed-page-ocr/README.md) |

The studies keep actual supported environments and unavailable-engine skips
distinct. A source-install command may provide the CLI/library without a bundled
UI; [development](development.md) explains how to build and package that UI.
