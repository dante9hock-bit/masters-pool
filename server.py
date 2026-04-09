#!/usr/bin/env python3
"""Simple HTTP server for the Masters Pool website."""

import http.server
import json
import os
import urllib.request
import urllib.parse
import time

PORT = int(os.environ.get("PORT", 8080))

# Supabase config
SUPABASE_URL = "https://fmpabvejsfitikfkkxg.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZtcGFidmVqc2ZpdGlrbWZra3hnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU2ODEzMjAsImV4cCI6MjA5MTI1NzMyMH0._3qRZ6l4EIGsLANeivH1VT9KTYUof10_KoldC9yyZKg"
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def supabase_request(method, path, body=None):
    """Make a request to Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else None
    headers = dict(SUPABASE_HEADERS)
    if method == "GET":
        headers["Accept"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        print(f"Supabase error: {e.code} {e.read().decode()}")
        return None
    except Exception as e:
        print(f"Supabase error: {e}")
        return None


def load_picks():
    """Load all picks from Supabase."""
    rows = supabase_request("GET", "picks?select=name,selections")
    if rows is None:
        return {}
    result = {}
    for row in rows:
        result[row["name"]] = row["selections"]
    return result


def save_pick(name, selections):
    """Save a single pick to Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/picks"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    body = json.dumps({"name": name, "selections": selections}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Supabase INSERT success: {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Supabase INSERT error: {e.code} {error_body}")
        return False
    except Exception as e:
        print(f"Supabase connection error: {e}")
        return False


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
        if self.path == "/api/debug":
            # Debug endpoint to test Supabase connection
            results = {}
            try:
                url = f"{SUPABASE_URL}/rest/v1/picks?select=name"
                headers = {
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Accept": "application/json",
                }
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    results["read_status"] = resp.status
                    results["read_data"] = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                results["read_error"] = f"{e.code}: {e.read().decode()}"
            except Exception as e:
                results["read_error"] = str(e)

            # Test write
            try:
                url = f"{SUPABASE_URL}/rest/v1/picks"
                headers = {
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                }
                body = json.dumps({"name": "__test__", "selections": {"1":"test"}}).encode()
                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    results["write_status"] = resp.status
                    results["write_data"] = resp.read().decode()
            except urllib.error.HTTPError as e:
                results["write_error"] = f"{e.code}: {e.read().decode()}"
            except Exception as e:
                results["write_error"] = str(e)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(results, indent=2).encode())
        elif self.path == "/api/picks":
            picks = load_picks()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(picks).encode())
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

            # Check if name already exists
            existing = load_picks()
            if name in existing:
                self.send_response(409)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Picks already submitted for this name"}).encode())
                return

            if save_pick(name, selections):
                print(f"PICK SAVED: {name} -> {json.dumps(selections)}")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Failed to save"}).encode())


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Masters Pool running at http://0.0.0.0:{PORT}")
    http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
