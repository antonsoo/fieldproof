# Public producer controls

`public.py` reads the pdfTeX and LibreOffice controls from
[py-pdf/sample-files at 02b8203](https://github.com/py-pdf/sample-files/tree/02b8203bf416db3dbdb03438bc8278dfcb0555f3).
Credit: the py-pdf sample-files contributors. The upstream repository licenses
these examples under [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).
The original examples' source documents and metadata remain available upstream.

The replay retains originals unchanged in its temporary output and creates one
modified pdfTeX control using pypdf: its `Name` field contains the invented
value `Example Form`. That modified PDF and all renders of these public
controls have the same CC BY-SA 4.0 license. The two names already in the
LibreOffice sample are upstream example values, not newly collected user data.
No upstream PDF, modified public PDF or public render is bundled with the package.

The separate files in `fixtures/` are authored synthetic ReportLab controls,
covered by this repository's MIT license. They describe no real transaction.
