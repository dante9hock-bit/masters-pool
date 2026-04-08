#!/usr/bin/env python3
"""Simple HTTP server for the Masters Pool website."""

import http.server
import json
import os
import urllib.request
import time

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "picks.json")
PORT = int(os.environ.get("PORT", 8080))


def load_picks():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_picks(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# Cache Masters scores to avoid hammering their server
_scores_cache = {"data": None, "time": 0}
SCORES_URL = "https://www.masters.com/en_US/scores/feeds/2026/scores.json"
CACHE_TTL = 60  # seconds


def fetch_masters_scores():
    now = time.time()
    if _scores_cache["data"] and (now - _scores_cache["time"]) < CACHE_TTL:
        return _scores_cache["data"]
    try:
        req = urllib.request.Request(SCORES_URL, headers={"User-Agent": "MastersPool/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            _scores_cache["data"] = raw
            _scores_cache["time"] = now
            return raw
    except Exception as e:
        print(f"Error fetching Masters scores: {e}")
        if _scores_cache["data"]:
            return _scores_cache["data"]
        return json.dumps({"error": str(e)}).encode()


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/picks":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(load_picks()).encode())
        elif self.path == "/api/scores":
            data = fetch_masters_scores()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "max-age=30")
            self.end_headers()
            self.wfile.write(data if isinstance(data, bytes) else data.encode())
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/picks":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            name = body.get("name", "").strip()
            selections = body.get("selections", {})

            if not name or len(selections) != 7:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Name and 7 tier selections required"}).encode())
                return

            picks = load_picks()
            picks[name] = selections
            save_picks(picks)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())

    def do_DELETE(self):
        if self.path.startswith("/api/picks/"):
            name = self.path.split("/api/picks/", 1)[1]
            from urllib.parse import unquote
            name = unquote(name)
            picks = load_picks()
            if name in picks:
                del picks[name]
                save_picks(picks)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Masters Pool running at http://0.0.0.0:{PORT}")
    http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
