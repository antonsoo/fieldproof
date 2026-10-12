import json
import pathlib
import subprocess
import sys
import time

import uno
from com.sun.star.beans import PropertyValue


def prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


proc = subprocess.Popen(
    [
        "soffice",
        "--headless",
        "--norestore",
        "--nodefault",
        "--accept=socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext",
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
try:
    resolver = uno.getComponentContext().ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", uno.getComponentContext()
    )
    for _ in range(100):
        try:
            ctx = resolver.resolve(
                "uno:socket,host=127.0.0.1,port=2002;urp;StarOffice.ComponentContext"
            )
            break
        except Exception:
            time.sleep(0.1)
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    results = []
    for arg in sys.argv[1:]:
        path = pathlib.Path(arg).resolve()
        modes = (
            [
                ("standard-formulas", "44,34,76,1,,1033,false,false,true,false,false,0,true"),
                ("standard-text-formulas", "44,34,76,1,,1033,false,false,true,false,false,0,false"),
            ]
            if path.suffix == ".csv"
            else [("workbook", None)]
        )
        for mode, opts in modes:
            props = [
                prop("Hidden", True),
                prop("ReadOnly", True),
                prop("UpdateDocMode", 0),
                prop(
                    "MacroExecutionMode",
                    uno.getConstantByName("com.sun.star.document.MacroExecMode.NEVER_EXECUTE"),
                ),
            ]
            if opts:
                props += [
                    prop("FilterName", "Text - txt - csv (StarCalc)"),
                    prop("FilterOptions", opts),
                ]
            doc = desktop.loadComponentFromURL(
                uno.systemPathToFileUrl(str(path)), "_blank", 0, tuple(props)
            )
            if doc is None:
                raise RuntimeError(f"Cannot open {path}")
            sheet = doc.Sheets.getByIndex(0)
            cursor = sheet.createCursor()
            cursor.gotoEndOfUsedArea(False)
            rows = []
            for r in range(cursor.RangeAddress.EndRow + 1):
                cells = []
                for c in range(7):
                    cell = sheet.getCellByPosition(c, r)
                    cells.append(
                        {
                            "text": cell.String,
                            "type": cell.Type.value,
                            "formula": cell.Formula,
                            "number": cell.Value,
                        }
                    )
                rows.append(cells)
            results.append({"file": arg, "mode": mode, "rows": rows})
            doc.close(True)
    print(
        json.dumps(
            {
                "version": subprocess.check_output(["soffice", "--version"], text=True).strip(),
                "results": results,
            },
            ensure_ascii=True,
            indent=2,
        )
    )
finally:
    proc.terminate()
    proc.wait(timeout=10)
