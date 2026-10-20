// Compare the old/new native browser export bytes without building a second UI.
import ts from "../../web/node_modules/typescript/lib/typescript.js";
import { readFileSync, writeFileSync, mkdirSync, symlinkSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve, join } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
const root = resolve(import.meta.dirname, "../..");
const base = process.argv[2],
    out = process.argv[3];
if (!base || !out)
    throw Error(
        "usage: node native_compatibility.mjs BASE_COMMIT OUTPUT_DIRECTORY",
    );
const data = JSON.parse(
    readFileSync(join(out, "native-after/extraction.json")),
);
const result = { baseline: base, scopes: {} };
const implementations = {};
for (const version of ["before", "after"]) {
    const target = join(out, `native-js-${version}`);
    mkdirSync(target, { recursive: true });
    try {
        symlinkSync(
            join(root, "web/node_modules"),
            join(target, "node_modules"),
            "dir",
        );
    } catch (e) {
        if (e.code !== "EEXIST") throw e;
    }
    for (const name of ["export", "review", "spreadsheet"]) {
        const file = `web/src/${name}.ts`;
        const source =
            version === "before"
                ? execFileSync("git", ["show", `${base}:${file}`], {
                      cwd: root,
                      encoding: "utf8",
                  })
                : readFileSync(join(root, file), "utf8");
        const js = ts
            .transpileModule(source, {
                compilerOptions: {
                    target: ts.ScriptTarget.ES2022,
                    module: ts.ModuleKind.ESNext,
                },
            })
            .outputText.replace(/from "\.\/(\w+)"/g, 'from "./$1.mjs"');
        writeFileSync(join(target, `${name}.mjs`), js);
    }
    implementations[version] = {
        ...(await import(pathToFileURL(join(target, "export.mjs")))),
        ...(await import(pathToFileURL(join(target, "spreadsheet.mjs")))),
    };
}
const digest = (b) => createHash("sha256").update(b).digest("hex");
for (const scope of ["all", "reviewed"]) {
    const bytes = {};
    for (const version of ["before", "after"]) {
        const m = implementations[version],
            rows = m.computeExportRows(data, scope);
        bytes[version] = {
            json: Buffer.from(JSON.stringify(rows)),
            csv: Buffer.from(m.rowsToCsv(rows)),
            xlsx: Buffer.from(m.rowsToXlsx(rows)),
        };
        for (const [extension, b] of Object.entries(bytes[version]))
            writeFileSync(
                join(out, `native-js-${version}`, `${scope}.${extension}`),
                b,
            );
    }
    result.scopes[scope] = {};
    for (const extension of ["json", "csv", "xlsx"]) {
        if (!bytes.before[extension].equals(bytes.after[extension]))
            throw Error(`${scope}.${extension} changed`);
        result.scopes[scope][extension] = {
            identical: true,
            sha256: digest(bytes.after[extension]),
            bytes: bytes.after[extension].length,
        };
    }
}
writeFileSync(
    join(out, "native-js-compatibility.json"),
    JSON.stringify(result, null, 2) + "\n",
);
console.log(JSON.stringify(result));
