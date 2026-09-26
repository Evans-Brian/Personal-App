import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from app import make_server

class VoiceTests(unittest.TestCase):
    def test_audio_endpoint_origin_limits_and_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            server=make_server(root/'vault',root/'data'/'oura.sqlite3',0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                def call(headers,body=b'audio'):
                    connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                    connection.request('POST','/api/transcribe',body,headers)
                    response=connection.getresponse();status=response.status;data=response.read();connection.close()
                    return status,data
                headers={'Origin':f'http://127.0.0.1:{server.server_port}','Content-Type':'audio/mp4'}
                with patch('voice.transcribe',return_value='A new task') as decode:
                    self.assertEqual(call({'Content-Type':'audio/mp4'})[0],403)
                    self.assertEqual(call({**headers,'Origin':'https://other.example'})[0],403)
                    self.assertEqual(call({**headers,'Content-Type':'text/plain'})[0],415)
                    self.assertEqual(call({**headers,'Content-Length':'99999999'})[0],413)
                    self.assertEqual(call(headers,b'')[0],413)
                    decode.assert_not_called()
                    status,body=call(headers)
                    self.assertEqual(status,200);self.assertIn(b'A new task',body)
                    decode.assert_called_once_with(b'audio')
                self.assertFalse((root/'vault'/'Journal').exists())
            finally:
                server.shutdown();server.server_close()
