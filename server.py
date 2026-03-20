"""
Icarus Live Map — combined HTTP server + save parser.

Start:  python server.py
Opens:  http://localhost:8080

GD.json is parsed on startup and re-parsed automatically whenever the file
changes (mtime-based).  No separate parse step needed.
Endpoint  GET /api/state  returns JSON with players, geysers, caves, deposits.
All other paths are served as static files from the same directory.
"""

import http.server
import json
import os
import threading
import webbrowser

import parse_players as pp

PORT    = 8080
GD_FILE = "GD.json"

os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ── State cache ───────────────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_parse_lock = threading.Lock()   # only one parse at a time
_cached = {"data": None, "mtime": 0.0, "version": 0}


def _do_parse(path, mtime):
    """Parse GD.json and update the cache.  Called while _parse_lock is held."""
    binary = pp.load_binary(path)

    blobs, _ = pp.parse_state_recorder_blobs(binary)
    cats     = pp.categorize(blobs)

    players  = pp.extract_players_compat(binary)
    geysers  = pp.extract_geysers(cats)
    caves    = pp.extract_caves_scan(binary)
    deposits = pp.extract_deposits_scan(binary)

    data = {
        "version":  0,          # filled in below under lock
        "players":  players,
        "geysers":  geysers,
        "caves":    caves,
        "deposits": deposits,
    }

    with _cache_lock:
        new_ver = _cached["version"] + 1
        data["version"] = new_ver
        _cached["data"]    = data
        _cached["mtime"]   = mtime
        _cached["version"] = new_ver

    e  = geysers.get("enzyme", [])
    o  = geysers.get("oil",    [])
    print(f"[+] Parsed v{new_ver} — "
          f"{len(players)} players | "
          f"{len(e)} enzyme / {len(o)} oil geysers | "
          f"{len(caves)} caves | "
          f"{len(deposits)} deposits")


def reparse_if_stale(path=GD_FILE):
    """Check mtime and reparse if GD.json has changed since last parse."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return

    with _cache_lock:
        if mtime <= _cached["mtime"]:
            return

    # Acquire parse lock non-blocking — drop the request if already parsing
    if not _parse_lock.acquire(blocking=False):
        return
    try:
        # Double-check after acquiring
        with _cache_lock:
            if mtime <= _cached["mtime"]:
                return
        _do_parse(path, mtime)
    except Exception as exc:
        print(f"[!] Parse error: {exc}")
    finally:
        _parse_lock.release()


# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.split("?")[0] == "/api/state":
            reparse_if_stale()
            with _cache_lock:
                data = _cached["data"]
            if data is None:
                self.send_error(503, "Savegame not yet parsed")
                return
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, fmt, *args):
        pass   # suppress per-request noise


# ── Startup ───────────────────────────────────────────────────────────────────
print(f"[+] Icarus Live Map  →  http://localhost:{PORT}")
print("    Ctrl+C to stop\n")

reparse_if_stale()

server = http.server.HTTPServer(("", PORT), Handler)
threading.Timer(0.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\n[+] Server stopped.")
