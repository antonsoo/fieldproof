using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using System.Text.Json;
var results = new List<object>();
var failures = 0;
foreach (var path in args) {
  using var doc = SpreadsheetDocument.Open(path, false);
  var errors = new OpenXmlValidator().Validate(doc).Select(e => new { e.Id, e.Description, Part = e.Part?.Uri.ToString(), Path = e.Path?.XPath }).ToList();
  failures += errors.Count;
  results.Add(new { file = path, errors });
}
Console.WriteLine(JsonSerializer.Serialize(results, new JsonSerializerOptions { WriteIndented = true }));
Environment.ExitCode = failures > 0 ? 1 : 0;
