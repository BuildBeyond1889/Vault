"""Vault Search: open the offline library in your browser.

    python tools/vault_app.py            (Open Vault.bat does this for you, or double-click Vault Search.exe)

Where the library is: a "zim" or "rachel" folder next to this program (so a drive with Vault Search.exe on it just
works), or else the folder the Get files saved into.

Starts two small web servers on this computer only (127.0.0.1):
  * port 8780: the Vault screen and its search
  * port 8781: the pages from the packs, kept on their own address so a page can never reach the Vault's controls
then opens the Vault in your browser. Nothing goes online.
"""
import json
import os
import time
import urllib.request
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FROZEN = getattr(sys, "frozen", False)          # running as "Vault Search.exe" (built with PyInstaller)
if FROZEN:
    BUNDLE = sys._MEIPASS                          # the pages and the pack list travel inside the program
    HERE = os.path.join(BUNDLE, "tools")
    ROOT = os.path.dirname(os.path.abspath(sys.executable))
    WEB = os.path.join(BUNDLE, "web")
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    DATA = os.path.join(base, "Vault Search")      # a drive handed around may be read-only, so notes live on this computer
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(HERE)
    WEB = os.path.join(ROOT, "web")
    DATA = os.path.join(ROOT, "data")
PORT = int(os.environ.get("VAULT_PORT", "8780"))
APP_VERSION = "1.1"     # bump when the page changes, so browsers never show an old copy
sys.path.insert(0, HERE)

# libzim's compiled code imports these; listing them here lets the packager (PyInstaller) see and include them
import datetime, enum, importlib.abc, pathlib, traceback, uuid, warnings  # noqa: E401,F401,E402

try:
    import libzim.reader  # noqa: F401
except ImportError as e:
    print("Vault Search needs the libzim package (%s). Run:  python -m pip install libzim" % e)
    sys.exit(1)
import vault  # noqa: E402

MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".css": "text/css",
        ".ttf": "font/ttf", ".woff2": "font/woff2", ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}


def find_library():
    """The library folder: next to the program first (a Vault drive), then the one the downloader remembers."""
    for d in (ROOT, os.path.dirname(ROOT)):
        if os.path.isdir(os.path.join(d, "zim")) or os.path.isdir(os.path.join(d, "rachel")):
            return d
    for cfg in (os.path.join(ROOT, "tools", "vault-folder.txt"), os.path.join(HERE, "vault-folder.txt")):
        try:
            with open(cfg, encoding="utf-8-sig") as f:
                d = f.read().strip().strip('"')
            if d:
                return d
        except OSError:
            pass
    return ""


def _hello(p):
    """Asks whatever is on port p whether it's Vault Search, and which version."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/app/hello" % p, timeout=1.5) as r:
            return json.loads(r.read() or b"{}")
    except Exception:      # noqa: BLE001
        return {}


def main():
    os.makedirs(DATA, exist_ok=True)
    where = os.path.join(DATA, "library-folder.txt")
    with open(where, "w", encoding="utf-8") as f:
        f.write(find_library())
    lib = vault.Vault(ROOT, DATA, folder_file=where, csv_path=os.path.join(HERE, "packs.csv"))
    port = [PORT]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", cache="no-store"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _file(self, rel):
            p = os.path.normpath(os.path.join(WEB, rel))
            if not p.startswith(os.path.normpath(WEB) + os.sep) or not os.path.isfile(p):
                return self._send(404, {"error": "not found"})
            with open(p, "rb") as f:
                self._send(200, f.read(), MIME.get(os.path.splitext(p)[1].lower(), "application/octet-stream"), "max-age=3600")

        def _local(self):
            return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

        def do_GET(self):
            if not self._local():
                return self._send(403, {"error": "not allowed"})
            u = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(u.query)
            path = u.path
            try:
                if path in ("/", "/index.html", "/vault.html", "/search.html"):   # one page: search, shelves and reading
                    with open(os.path.join(WEB, "vault.html"), encoding="utf-8") as f:
                        page = f.read().replace('<html lang="en">', '<html lang="en" data-skin="public">', 1)
                    return self._send(200, page, MIME[".html"])
                if path.startswith("/fonts/"):
                    return self._file(urllib.parse.unquote(path[1:]))
                if path == "/api/app/hello":
                    return self._send(200, {"app": "vault-search", "version": APP_VERSION})
                if path == "/api/vault/icon":
                    got = lib.icon((qs.get("id") or [""])[0])
                    return self._send(200, got[0], got[1], "max-age=86400") if got else self._send(404, {"error": "no icon"})
                if path.startswith("/api/vault/"):
                    return self._send(200, lib.get(path[11:], lambda k, d="": (qs.get(k) or [d])[0]))
                return self._send(404, {"error": "not found"})
            except Exception as e:      # noqa: BLE001
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            origin = self.headers.get("Origin") or ""
            origin_ok = ("http://127.0.0.1:%d" % port[0], "http://localhost:%d" % port[0])
            if not self._local() or (origin and not origin.startswith(origin_ok)):
                return self._send(403, {"error": "not allowed"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                body = {}
            path = urllib.parse.urlparse(self.path).path
            try:
                if path == "/api/app/quit":       # a newer Vault Search asks this older one to step aside
                    self._send(200, {"ok": True})
                    threading.Timer(0.2, lambda: os._exit(0)).start()   # exit right away so the port frees up
                    return
                if path.startswith("/api/vault/"):
                    return self._send(200, lib.post(path[11:], body))
                return self._send(404, {"error": "not found"})
            except Exception as e:      # noqa: BLE001
                return self._send(500, {"error": str(e)})

    class S(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

    server_ref = [None]
    server = None
    for p in range(PORT, PORT + 20, 2):        # each copy needs two ports: the screen and the pages
        try:
            server = S(("127.0.0.1", p), H)
            port[0] = p
            break
        except OSError:
            pass
        other = _hello(p)
        if other.get("version") == APP_VERSION:  # this same version is already open: just show it
            print("Vault Search is already open. Showing it in your browser.")
            webbrowser.open("http://127.0.0.1:%d/?v=%s" % (p, APP_VERSION))
            return
        if other.get("app") == "vault-search":   # an older copy: ask it to close, then take its place
            print("Closing an older Vault Search that was still running...")
            try:
                req = urllib.request.Request("http://127.0.0.1:%d/api/app/quit" % p, data=b"{}", method="POST",
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=3).read()
            except Exception:      # noqa: BLE001  (very old copies can't be asked; we just use the next port)
                pass
            for _ in range(10):
                time.sleep(0.3)
                try:
                    server = S(("127.0.0.1", p), H)
                    port[0] = p
                    break
                except OSError:
                    pass
            if server:
                break
    if not server:
        print("Couldn't find a free port for Vault Search. Restart the computer and try again.")
        input("Press Enter to close.")
        return
    server_ref[0] = server
    try:
        lib.start_content(port[0] + 1)
    except OSError:
        print("Port %d is busy, so pages from the packs may not open. Close other copies and try again." % (port[0] + 1))
    url = "http://127.0.0.1:%d/?v=%s" % (port[0], APP_VERSION)   # the ?v= part stops the browser reusing an old page
    print("Vault Search is running at %s" % url)
    print("Keep this window open while you read. Close it to stop.")
    if not lib.folder():
        print("No library found: put this next to a zim folder, or run one of the Get ... .bat files first.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
