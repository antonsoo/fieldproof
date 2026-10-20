# CORD v2 test receipt 0

The receipt photograph and annotations are from **CORD**, published by
**NAVER CLOVA / the CORD contributors**, under the
[Creative Commons Attribution 4.0 International license](https://creativecommons.org/licenses/by/4.0/).
The authors identify that license in the [CORD repository](https://github.com/clovaai/cord).

Source: [naver-clova-ix/cord-v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2/tree/7f0115a4b758a71d6473b8d085751692da2fef98),
revision `7f0115a4b758a71d6473b8d085751692da2fef98`, test split, row 0.
`source.json` identifies the exact image and its containing Parquet file.

`cord-test-0000.pdf` wraps the unchanged photograph in an image-only PDF at
144 dpi. Its embedded RGB pixels match the original. The wrapper adds source
and license credit to PDF metadata. This is an adaptation of the container;
no image pixels are edited. The source photograph already has a redacted
header. There is no usable merchant name or transaction date in this example.

`fixture.json` contains **authored extraction claims**, not a model's output.
The item and total use the supplied annotations. The amount `60.000` is
represented as 60,000 in the fixture; the file's number conventions still need
review. The total's evidence quote supplies the printed line context.
Required merchant/date strings are empty and have no evidence, preserving
unprovided values instead of inventing a name or date. No OCR or extraction
accuracy benchmark is claimed by this example.

See the [original work and data specification](https://github.com/clovaai/cord)
and the [local review study](https://github.com/antonsoo/fieldproof/blob/main/studies/server-ocr/README.md).
The surrounding Fieldproof code is MIT licensed; the receipt photograph and
annotations retain CC BY 4.0.
