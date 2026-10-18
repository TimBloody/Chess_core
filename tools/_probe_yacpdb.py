import json
import urllib.request

HEADERS = {"User-Agent": "ChessCoreEducation/1.0"}
url = "https://www.yacpdb.org/json.php?entry&id=300000"
req = urllib.request.Request(url, headers=HEADERS)
data = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
out = {
    "id": data.get("id"),
    "stipulation": data.get("stipulation"),
    "authors": data.get("authors"),
    "algebraic": data.get("algebraic"),
    "options": data.get("options"),
    "keywords": data.get("keywords"),
    "solution": data.get("solution"),
    "source": data.get("source"),
}
path = "tools/_yacpdb_sample.json"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(out, handle, ensure_ascii=False, indent=2)
print("wrote", path, "stip", out["stipulation"])
