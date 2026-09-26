import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from app import make_server

class RemoteAccessTests(unittest.TestCase):
    def test_private_proxy_identity_origin_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            origin='https://journal.example.ts.net'
            server=make_server(root/'vault',root/'data'/'oura.sqlite3',0,{'origin':origin,'login':'owner@example.com'})
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                def request(method,path,headers,body=None):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                    conn.request(method,path,body,headers)
                    response=conn.getresponse();status=response.status;data=response.read();conn.close()
                    return status,json.loads(data)
                headers={'Host':'journal.example.ts.net','Tailscale-User-Login':'owner@example.com','Origin':origin,'Content-Type':'application/json'}
                status,entry=request('GET','/api/entry?date=2026-09-26',headers)
                self.assertEqual(status,200)
                body=json.dumps({'date':entry['date'],'period':'morning','content':'Remote test','revision':entry['revision']})
                self.assertEqual(request('POST','/api/entry',headers,body)[0],200)
                for overrides in [{'Origin':'https://evil.example'},{'Tailscale-User-Login':'other@example.com'},{'Host':'evil.example'}]:
                    self.assertEqual(request('GET','/api/config',{**headers,**overrides})[0],403)
                self.assertEqual(request('GET','/api/config',{'Host':'journal.example.ts.net'})[0],403)
                self.assertEqual(request('GET','/api/config',{})[0],200)
            finally:
                server.shutdown();server.server_close()
