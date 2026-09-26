"""Double-click the installed shortcut. --background is used at Windows sign-in."""
import ctypes
import json
import sys
import webbrowser
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent

URL = 'http://127.0.0.1:8765'


def main():
    from app import configured_vault, configured_remote, make_server
    try:
        with urlopen(URL + '/api/config', timeout=2) as response:
            running = json.load(response)
        if running.get('app') != 'personal-journal' or running.get('vault') != str(configured_vault().resolve()):
            raise RuntimeError('Port 8765 is already in use by a different app or vault.')
        if '--background' not in sys.argv:
            webbrowser.open(URL)
        logging.info('Reused the running journal.')
        return
    except (ConnectionError, OSError):
        pass
    server = make_server(configured_vault(), ROOT / 'data' / 'oura.sqlite3', remote=configured_remote())
    server.oura_sync.start_worker()
    logging.info('Journal listening on %s', URL)
    if '--background' not in sys.argv:
        webbrowser.open(URL)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    log_dir = ROOT / 'data'
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / 'startup.log', maxBytes=100_000, backupCount=2, encoding='utf-8')
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    attempts = 7 if '--background' in sys.argv else 1
    for attempt in range(attempts):
        try:
            logging.info('Starting journal (attempt %s).', attempt+1)
            main()
            break
        except Exception as exc:
            logging.exception('Journal startup or server failed.')
            if attempt+1 < attempts:
                time.sleep(10)
            elif '--background' not in sys.argv:
                ctypes.windll.user32.MessageBoxW(0, str(exc), 'Personal Journal could not start', 0x10)
