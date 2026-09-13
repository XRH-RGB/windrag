import sys, tempfile, threading, unittest, json
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s

class LoginLifecycle(unittest.TestCase):
    def test_accounts_survive_logout_and_service_restart(self):
        old=s.DATA
        with tempfile.TemporaryDirectory() as directory:
            s.DATA=Path(directory)
            try:
                for restart in range(2):
                    s.init_db()
                    http=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler)
                    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
                    base=f'http://127.0.0.1:{http.server_port}/api/'
                    try:
                        for username,password in [('admin','admin123'),('operator','operator123'),('user','user123'),('engineer','Wind@2026!'),('librarian','Wind@2026!')]:
                            client=build_opener(HTTPCookieProcessor(CookieJar()))
                            def call(path,body=None):
                                req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-WindRAG':'1'})
                                try:
                                    with client.open(req) as response:return response.status,json.load(response)
                                except HTTPError as e:return e.code,json.load(e)
                            for attempt in range(13 if username=='user' else 2):
                                status,result=call('login',{'username':username,'password':password,'remember':True})
                                self.assertEqual(status,200,(restart,username,attempt,result))
                                self.assertEqual(call('me')[1]['user']['username'],username)
                                self.assertEqual(call('logout',{})[0],200)
                                self.assertEqual(call('me')[0],401)
                    finally:http.shutdown();http.server_close();thread.join()
            finally:s.DATA=old

if __name__=='__main__':unittest.main()
