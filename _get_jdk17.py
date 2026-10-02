import urllib.request, zipfile, shutil, os, time
from pathlib import Path

URLS = [
    ("microsoft", "https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip"),
    ("adoptium", "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13+11/OpenJDK17U-jdk_x64_windows_hotspot_17.0.13_11.zip"),
]
DEST_DIR = Path.home() / "java" / "17.0.13+11"

if (DEST_DIR / "bin" / "javac.exe").exists():
    print("JDK17 already present:", DEST_DIR)
    raise SystemExit(0)

DEST_DIR.parent.mkdir(parents=True, exist_ok=True)
for name, url in URLS:
    tmp_zip = DEST_DIR.parent / "_jdk17_tmp.zip"
    try:
        print("trying:", name, url, flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=1800) as resp, open(tmp_zip, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            done = 0
            last_pct = -1
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct != last_pct and pct % 5 == 0:
                        last_pct = pct
                        print(f"  {done/1048576:.1f}/{total/1048576:.1f} MB ({pct}%) {int(time.time()-t0)}s", flush=True)
        print("downloaded %.1f MB in %d s" % (done / 1048576, int(time.time() - t0)), flush=True)

        extract_tmp = DEST_DIR.parent / "_extract_tmp"
        shutil.rmtree(extract_tmp, ignore_errors=True)
        with zipfile.ZipFile(tmp_zip) as z:
            z.extractall(extract_tmp)
        top = [p for p in extract_tmp.iterdir() if p.is_dir()]
        root = top[0] if len(top) == 1 else extract_tmp
        DEST_DIR.mkdir(parents=True, exist_ok=True)
        for item in os.listdir(root):
            shutil.move(str(root / item), str(DEST_DIR))
        shutil.rmtree(extract_tmp, ignore_errors=True)
        os.remove(tmp_zip)
        print("extracted OK from", name, flush=True)
        break
    except Exception as e:
        print("failed:", name, type(e).__name__, str(e)[:120], flush=True)
        if tmp_zip.exists():
            try: tmp_zip.unlink()
            except OSError: pass
        continue

print("FINAL javac exists:", (DEST_DIR / "bin" / "javac.exe").exists())
