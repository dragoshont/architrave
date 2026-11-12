using System.Text.Json;
using ParcelDesk;

var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
foreach (var line in ReadLines())
{
    var clearance = JsonSerializer.Deserialize<Clearance>(line, options)
        ?? throw new ArgumentException("Clearance required");
    Console.WriteLine(JsonSerializer.Serialize(new { released = ReleasePolicy.CanRelease(clearance) }));
}

static IEnumerable<string> ReadLines()
{
    string? line;
    while ((line = Console.ReadLine()) != null)
        yield return line;
}
