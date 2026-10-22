"""Oura daily summaries via OAuth; no journal text leaves the computer."""
from datetime import date, timedelta, datetime, timezone
import json
import secrets
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from secrets_store import SecretStore

KINDS = ('daily_sleep', 'daily_readiness', 'daily_activity', 'sleep')
OPTIONAL_KINDS = ('daily_spo2', 'sleep_time', 'daily_stress')


class OuraAPIError(ValueError):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def fetch_json(request):
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as exc:
        messages = {401: 'Oura authorization expired. Reconnect your account.',
                    403: 'Oura denied daily-summary access. Check permissions and membership.',
                    429: 'Oura rate limit reached. Try again later.'}
        raise OuraAPIError(messages.get(exc.code, f'Oura request failed (HTTP {exc.code}).'), exc.code) from None
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ValueError('Could not reach Oura. Check your connection and try again.') from None


class OuraSync:
    def __init__(self, store, secret_path, port):
        self.store = store
        self.secrets = SecretStore(secret_path)
        self.redirect_uri = f'http://localhost:{port}/api/oura/callback'
        self.port = port
        self.lock = threading.RLock()
        self.states = {}
        self.starts = {}
        self.error = None
        self.syncing = False
        self.stop = threading.Event()
        self.last_attempt = 0
        self.history_running = False
        self.history_progress = None
        self.history_lock = threading.Lock()

    def status(self):
        # Credential files are replaced atomically; progress must remain readable during an import.
        saved = self.secrets.read()
        return {'configured': bool(saved.get('client_id')), 'connected': bool(saved.get('refresh_token')),
                'last_sync': saved.get('last_sync'), 'error': self.error,
                'syncing': self.syncing, 'redirect_uri': self.redirect_uri,
                'history_running': self.history_running, 'history_progress': self.history_progress,
                'history_imported_at': saved.get('history_imported_at'),
                'optional_unavailable': saved.get('optional_unavailable', [])}

    def configure(self, client_id, client_secret):
        if not all(isinstance(x, str) and 0 < len(x.strip()) < 2000 for x in (client_id, client_secret)):
            raise ValueError('Enter both the Oura client ID and client secret.')
        with self.lock:
            current = self.secrets.read()
            if current.get('refresh_token'):
                raise ValueError('Disconnect before replacing Oura app credentials.')
            self.secrets.write({'client_id': client_id.strip(), 'client_secret': client_secret.strip()})

    def begin(self):
        with self.lock:
            saved = self.secrets.read()
            if not saved.get('client_id'):
                raise ValueError('Save your Oura app credentials first.')
            state, cookie = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.states = {state: (cookie, time.time() + 600)}
            url = 'https://cloud.ouraring.com/oauth/authorize?' + urlencode({
                'response_type': 'code', 'client_id': saved['client_id'],
                'redirect_uri': self.redirect_uri, 'scope': 'daily spo2', 'state': state})
            ticket = secrets.token_urlsafe(32)
            self.starts = {ticket: (url, cookie, time.time()+600)}
            return f'http://localhost:{self.port}/api/oura/authorize?ticket={ticket}'

    def authorize(self, ticket):
        with self.lock:
            pending = self.starts.pop(ticket, None)
            if not pending or pending[2] < time.time():
                raise ValueError('Oura connection expired. Start Connect again.')
            return pending[0], pending[1]

    def exchange(self, values):
        saved = self.secrets.read()
        body = urlencode({**values, 'client_id': saved['client_id'],
                          'client_secret': saved['client_secret']}).encode()
        token = fetch_json(Request('https://api.ouraring.com/oauth/token', data=body,
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'}))
        if not all(isinstance(token.get(k), str) and token[k] for k in ('access_token', 'refresh_token')):
            raise ValueError('Oura returned an incomplete authorization. Please reconnect.')
        saved.update(access_token=token['access_token'], refresh_token=token['refresh_token'],
                     expires_at=time.time() + float(token.get('expires_in', 3600)))
        self.secrets.write(saved)  # Persist each rotating refresh token immediately.
        return saved['access_token']

    def callback(self, state, cookie, code, error=None):
        with self.lock:
            pending = self.states.pop(state, None)
            if not pending or pending[1] < time.time() or not secrets.compare_digest(pending[0], cookie):
                raise ValueError('Oura connection expired or came from a different browser. Start Connect again.')
            if error or not code:
                raise ValueError('Oura connection was not authorized. You can try again.')
            self.exchange({'grant_type': 'authorization_code', 'code': code, 'redirect_uri': self.redirect_uri})
            self.error = None

    def disconnect(self):
        with self.lock:
            saved = self.secrets.read()
            self.secrets.write({k: saved[k] for k in ('client_id', 'client_secret') if k in saved})
            self.states.clear()
            self.starts.clear()
            self.error = None

    def start_history(self):
        if not self.history_lock.acquire(blocking=False):
            return False
        if not self.status()['connected']:
            self.history_lock.release()
            raise ValueError('Connect your Oura account first.')
        self.history_running = True
        self.history_progress = {'collection': 'starting', 'records': 0}
        def run():
            try:
                self.sync(history=True)
            except (ValueError, OSError) as exc:
                self.error = str(exc)
            finally:
                self.history_running = False
                self.history_lock.release()
        threading.Thread(target=run, daemon=True).start()
        return True

    def sync(self, history=False):
        with self.lock:
            self.syncing = True
            self.last_attempt = time.time()
        try:
            # Serialize credential refresh, import and disconnect across all callers.
            with self.lock:
                saved = self.secrets.read()
                if not saved.get('refresh_token'):
                    raise ValueError('Connect your Oura account first.')
                token = saved.get('access_token')
                if time.time() >= saved.get('expires_at', 0) - 120:
                    token = self.exchange({'grant_type': 'refresh_token', 'refresh_token': saved['refresh_token']})
                start = date(2015, 1, 1) if history else date.today() - timedelta(days=30 if saved.get('last_sync') else 90)
                end = date.today() + timedelta(days=1)
                count = 0
                unavailable = []
                for kind in KINDS + OPTIONAL_KINDS:
                    kind_start = date.today() - timedelta(days=90) if not history and kind == 'sleep' and not saved.get('sleep_details_imported') else start
                    next_token = None
                    seen = set()
                    for _ in range(100):
                        params = {'start_date': kind_start.isoformat(), 'end_date': end.isoformat()}
                        if next_token:
                            params['next_token'] = next_token
                        url = f'https://api.ouraring.com/v2/usercollection/{kind}?' + urlencode(params)
                        if history:
                            self.history_progress = {'collection': kind, 'records': count}
                        # Long imports can cross an access-token expiry boundary.
                        if time.time() >= self.secrets.read().get('expires_at', 0) - 120:
                            latest = self.secrets.read()
                            token = self.exchange({'grant_type': 'refresh_token', 'refresh_token': latest['refresh_token']})
                        try:
                            result = fetch_json(Request(url, headers={'Authorization': f'Bearer {token}'}))
                        except OuraAPIError as exc:
                            # Oura also returns 401 for a collection outside the granted scopes.
                            # Core daily collections have already succeeded with this same token.
                            if kind in OPTIONAL_KINDS and exc.status in (401, 403, 404):
                                unavailable.append(kind)
                                break
                            raise
                        records = result.get('data')
                        if not isinstance(records, list):
                            raise ValueError('Oura returned an unexpected summary format.')
                        self.store.import_records(kind, records)
                        count += len(records)
                        next_token = result.get('next_token')
                        if not next_token:
                            break
                        if not isinstance(next_token, str) or next_token in seen:
                            raise ValueError('Oura pagination did not complete. Try again later.')
                        seen.add(next_token)
                    else:
                        raise ValueError('Oura import exceeded its page limit. Try again later.')
                latest = self.secrets.read()
                latest['last_sync'] = datetime.now(timezone.utc).isoformat()
                latest['sleep_details_imported'] = True
                latest['optional_unavailable'] = unavailable
                if history:
                    latest['history_imported_at'] = latest['last_sync']
                    self.history_progress = {'collection': 'complete', 'records': count}
                self.secrets.write(latest)
                self.error = None
                return count
        except ValueError as exc:
            self.error = str(exc)
            raise
        finally:
            self.syncing = False

    def start_worker(self):
        def run():
            while not self.stop.wait(30):
                try:
                    if self.status()['connected'] and time.time() - self.last_attempt >= 3600:
                        self.sync()
                except (ValueError, OSError):
                    pass  # Visible via status; retry at most hourly.
        threading.Thread(target=run, daemon=True).start()
