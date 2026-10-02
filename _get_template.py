import urllib.request, zipfile, shutil, os, time
from pathlib import Path

URL = "https://github.com/flet-dev/flet-build-template/archive/refs/heads/0.28.3.zip"
CACHE = Path("C:/Users/DavisStark/PycharmProjects/word_app/_template_cache")
CACHE.mkdir(parents=True, exist_ok=True)
tmp_zip = CACHE / "_tpl.zip"

print("downloading:", URL, flush=True)
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=600) as resp, open(tmp_zip, "wb") as f:
    total = int(resp.headers.get("Content-Length", 0) or 0)
    done = 0
    while True:
        chunk = resp.read(1024 * 256)
        if not chunk:
            break
        f.write(chunk)
        done += len(chunk)
print("downloaded %.2f MB in %d s" % (done / 1048576, int(time.time() - t0)), flush=True)

shutil.rmtree(CACHE / "_extract", ignore_errors=True)
(CACHE / "_extract").mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(tmp_zip) as z:
    z.extractall(CACHE / "_extract")
tmp_zip.unlink()
top = [p.name for p in (CACHE / "_extract").iterdir()]
print("extracted top dirs:", top)
