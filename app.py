"""Run with python app.py; listens only on this computer."""
import argparse
import json
import socket
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from journal import Journal, Conflict
from restaurants import Restaurants
from people import People
from oura import OuraStore
from oura_sync import OuraSync
from sleep_analysis import analyze as analyze_sleep
from bjj import BJJLibrary

ROOT = Path(__file__).resolve().parent


def configured_vault():
    config = ROOT / "config.local.json"
    if not config.exists():
        return ROOT / "demo-vault"
    value = json.loads(config.read_text(encoding="utf-8"))["vault"]
    vault = Path(value)
    if not vault.is_absolute() or not vault.is_dir():
        raise ValueError("The configured vault must be an existing absolute folder path.")
    return vault


def configured_remote():
    config = ROOT / "config.local.json"
    return json.loads(config.read_text(encoding="utf-8")).get("remote_access", {}) if config.exists() else {}


def configured_bjj_library():
    config = ROOT / "config.local.json"
    value = json.loads(config.read_text(encoding="utf-8")).get("bjj_library") if config.exists() else None
    return Path(value) if value else ROOT / "data" / "bjj-library"


def configured_sleep_start():
    config = ROOT / "config.local.json"
    return json.loads(config.read_text(encoding="utf-8")).get("sleep_analysis_start") if config.exists() else None


def make_server(vault, database, port=8765, remote=None, bjj_root=None, sleep_start=None):
    remote = remote or {}
    remote_origin = remote.get('origin', '')
    remote_login = remote.get('login', '')
    if remote_origin:
        parsed = urlsplit(remote_origin)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.ts.net') or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.port or not remote_login:
            raise ValueError('Remote access requires an exact Tailscale HTTPS origin and account login.')
    journal = Journal(vault)
    restaurants = Restaurants(vault)
    people = People(vault)
    bjj = BJJLibrary(bjj_root or ROOT / "data" / "bjj-library", vault)
    if Path(database).resolve().is_relative_to(journal.vault):
        raise ValueError("Keep the SQLite database outside your Obsidian vault.")
    oura = OuraStore(database)
    sync = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log journal content or request dates.

        def respond(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            raw = json.dumps(body).encode() if isinstance(body, dict) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            host = self.headers.get('Host')
            local_hosts = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
            identity = self.headers.get('Tailscale-User-Login')
            if identity is not None or (remote_origin and host == urlsplit(remote_origin).netloc):
                return bool(remote_origin and identity == remote_login and
                            host in (*local_hosts, urlsplit(remote_origin).netloc) and
                            self.headers.get('Origin', remote_origin) == remote_origin)
            return host in local_hosts and self.headers.get('Origin', f'http://{host}') == f'http://{host}'

        def local_only(self):
            host = self.headers.get('Host')
            local_hosts = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
            return host in local_hosts and self.headers.get('Origin', f'http://{host}') == f'http://{host}'

        def serve_bjj_media(self, media_id):
            try:
                _, path = bjj.entry(media_id)
            except ValueError:
                return self.respond(404, {"error": "Media not found."})
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range")
            if header:
                match = __import__('re').fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
                if not match or (not match.group(1) and not match.group(2)):
                    return self.respond(416, {"error": "Invalid byte range."}, headers={"Content-Range": f"bytes */{size}"})
                if match.group(1):
                    start = int(match.group(1)); end = int(match.group(2)) if match.group(2) else size - 1
                else:
                    suffix = int(match.group(2)); start = max(0, size - suffix); end = size - 1
                if start >= size or start > end:
                    return self.respond(416, {"error": "Range is outside the media file."}, headers={"Content-Range": f"bytes */{size}"})
                end = min(end, size - 1); status = 206
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}") if status == 206 else None
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                try:
                    while remaining:
                        block = source.read(min(1024 * 1024, remaining))
                        if not block:
                            break
                        self.wfile.write(block); remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # Browsers routinely cancel an old range request after a seek.

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {"error": "Open the app using its local address or configured private Tailscale address."})
            url = urlsplit(self.path)
            try:
                if url.path == "/api/people":
                    return self.respond(200, people.read())
                if url.path == "/api/restaurants":
                    return self.respond(200, restaurants.read())
                if url.path == "/api/entry":
                    return self.respond(200, journal.read(parse_qs(url.query).get("date", [""])[0]))
                if url.path == '/api/carryover':
                    return self.respond(200, journal.carryover(parse_qs(url.query).get('date', [''])[0]))
                if url.path == "/api/config":
                    return self.respond(200, {"vault": str(journal.vault), "app": "personal-journal", "version": 2})
                if url.path == '/api/entries':
                    return self.respond(200, {'entries': journal.history()})
                if url.path == '/api/tasks':
                    return self.respond(200, {'tasks': journal.task_history(write=True)})
                if url.path == '/api/bjj/library':
                    return self.respond(200, bjj.library())
                if url.path == '/api/bjj/transcript':
                    return self.respond(200, bjj.transcript(parse_qs(url.query).get('media_id', [''])[0]))
                if url.path == '/api/bjj/search':
                    query = parse_qs(url.query)
                    return self.respond(200, {'results': bjj.search(
                        query.get('q', [''])[0], query.get('course', [''])[0], query.get('volume', [''])[0],
                        query.get('chapter', [''])[0], query.get('semantic', ['0'])[0] == '1',
                        limit=query.get('limit', ['30'])[0], source=query.get('source', ['bjj'])[0],
                    )})
                if url.path == '/api/bjj/notes':
                    return self.respond(200, {'notes': bjj.notes()})
                if url.path == '/api/bjj/training':
                    return self.respond(200, bjj.training(parse_qs(url.query).get('date', [''])[0]))
                if url.path == '/api/bjj/training-history':
                    query = parse_qs(url.query)
                    return self.respond(200, bjj.training_history(
                        query.get('q', [''])[0], query.get('rating', [''])[0],
                        query.get('limit', ['20'])[0], query.get('offset', ['0'])[0],
                    ))
                if url.path == '/api/bjj/ai-credentials':
                    if not self.local_only():
                        return self.respond(403, {"error": "AI credentials can only be managed on this computer."})
                    return self.respond(200, bjj.ai_status())
                if url.path.startswith('/api/bjj/media/'):
                    return self.serve_bjj_media(url.path.removeprefix('/api/bjj/media/'))
                if url.path == '/api/oura/status':
                    return self.respond(200, sync.status())
                if url.path == '/api/oura/authorize':
                    target, cookie = sync.authorize(parse_qs(url.query).get('ticket', [''])[0])
                    return self.respond(303, b'', headers={'Location': target, 'Set-Cookie': f'oura_state={cookie}; HttpOnly; SameSite=Lax; Path=/api/oura/callback; Max-Age=600'})
                if url.path == '/api/oura/day':
                    day = parse_qs(url.query).get('date', [''])[0]
                    journal.path(day)
                    return self.respond(200, {'records': oura.read_range(day, day)})
                if url.path == '/api/oura/sleep-analysis':
                    query = parse_qs(url.query)
                    return self.respond(200, analyze_sleep(oura, journal, query.get('start', [None])[0], query.get('end', [None])[0], analysis_start=sleep_start))
                if url.path == '/api/oura/callback':
                    query = parse_qs(url.query)
                    cookies = SimpleCookie(self.headers.get('Cookie', ''))
                    cookie = cookies.get('oura_state')
                    sync.callback(query.get('state', [''])[0], cookie.value if cookie else '',
                                  query.get('code', [''])[0], query.get('error', [None])[0])
                    return self.respond(303, b'', headers={'Location': f'http://127.0.0.1:{self.server.server_port}/', 'Set-Cookie': 'oura_state=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/api/oura/callback'})
                assets = {"/people.js": ("people.js", "text/javascript"), "/restaurants.js": ("restaurants.js", "text/javascript"), "/plans.js": ("plans.js", "text/javascript"), "/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                assets["/voice.js"] = ("voice.js", "text/javascript")
                assets["/bjj.js"] = ("bjj.js", "text/javascript")
                assets["/sleep.js"] = ("sleep.js", "text/javascript")
                assets["/sleep.css"] = ("sleep.css", "text/css")
                assets.update({f"/icon-{size}.png": (f"icon-{size}.png", "image/png") for size in (180,192,512)})
                assets["/manifest.webmanifest"] = ("manifest.webmanifest", "application/manifest+json")
                if url.path in assets:
                    name, mime = assets[url.path]
                    return self.respond(200, (ROOT / "static" / name).read_bytes(), mime if mime == "image/png" else mime + "; charset=utf-8")
                self.respond(404, {"error": "Not found"})
            except (ValueError, OSError, RuntimeError) as exc:
                self.respond(400, {"error": str(exc)})

        def do_POST(self):
            if self.path == '/api/transcribe':
                if not self.allowed() or self.headers.get('Origin') is None:
                    return self.respond(403, {'error': 'Only requests from this app are accepted.'})
                from voice import MAX_BYTES, VoiceUnavailable, transcribe
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= MAX_BYTES:
                        return self.respond(413, {'error': 'Recording is empty or too large. Keep it under two minutes.'})
                    if self.headers.get('Content-Type', '').split(';')[0] not in ('audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav'):
                        return self.respond(415, {'error': 'Unsupported audio format.'})
                    self.connection.settimeout(180)
                    return self.respond(200, {'text': transcribe(self.rfile.read(length))})
                except ValueError as exc:
                    return self.respond(400, {'error': str(exc)})
                except VoiceUnavailable as exc:
                    return self.respond(503, {'error': str(exc)})
                except Exception:
                    return self.respond(503, {'error': 'Local transcription could not finish. Try recording again.'})
            if not self.allowed() or self.headers.get("Content-Type") != "application/json":
                return self.respond(403, {"error": "Only same-origin JSON requests are accepted."})
            if self.path not in ('/api/people', '/api/restaurants', '/api/entry', '/api/oura/setup', '/api/oura/connect', '/api/oura/sync', '/api/oura/history', '/api/oura/disconnect', '/api/bjj/note', '/api/bjj/training', '/api/bjj/ai-credentials'):
                return self.respond(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    raise ValueError("Invalid request size.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Expected an entry object.")
                if self.path == '/api/people':
                    return self.respond(200, people.add(data))
                if self.path == '/api/restaurants':
                    return self.respond(200, restaurants.save(data.get('restaurants'), data.get('revision')))
                if self.path == '/api/bjj/note':
                    return self.respond(200, bjj.save_note(data))
                if self.path == '/api/bjj/training':
                    return self.respond(200, bjj.save_training(data))
                if self.path == '/api/bjj/ai-credentials':
                    if not self.local_only():
                        return self.respond(403, {"error": "AI credentials can only be managed on this computer."})
                    return self.respond(200, bjj.save_ai_credentials(data))
                if self.path == '/api/oura/setup':
                    sync.configure(data.get('client_id'), data.get('client_secret'))
                    return self.respond(200, sync.status())
                if self.path == '/api/oura/connect':
                    return self.respond(200, {'url': sync.begin()})
                if self.path == '/api/oura/sync':
                    return self.respond(200, {'imported': sync.sync()})
                if self.path == '/api/oura/history':
                    started = sync.start_history()
                    return self.respond(202, {'started': started, **sync.status()})
                if self.path == '/api/oura/disconnect':
                    sync.disconnect()
                    return self.respond(200, sync.status())
                result = journal.save(data.get("date"), data.get("period"), data.get("content"), data.get("revision"))
                self.respond(200, result)
            except Conflict as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, TypeError, OSError) as exc:
                self.respond(400, {"error": str(exc)})

    class LocalServer(ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def server_close(self):
            if sync:
                sync.stop.set()
            super().server_close()

    server = LocalServer(("127.0.0.1", port), Handler)
    sync = OuraSync(oura, Path(database).parent / 'oura-secrets.bin', server.server_port)
    server.oura_sync = sync
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "oura.sqlite3")
    parser.add_argument("--bjj-library", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    args.vault = args.vault if args.vault is not None else configured_vault()
    server = make_server(args.vault, args.database, args.port, configured_remote(), args.bjj_library or configured_bjj_library(), sleep_start=configured_sleep_start())
    server.oura_sync.start_worker()
    print(f"Journal ready: http://127.0.0.1:{server.server_port} | Vault: {args.vault.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
