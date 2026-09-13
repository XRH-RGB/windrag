import sys, tempfile, socket, threading, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import launcher
from urllib.request import urlopen

class LaunchTests(unittest.TestCase):
    def test_occupied_port_fallback_and_repeat_reuse(self):
        old=launcher.server.DATA
        with tempfile.TemporaryDirectory() as folder:
            launcher.server.DATA=Path(folder)
            blocker=socket.socket();blocker.bind(('127.0.0.1',0));blocker.listen()
            port=blocker.getsockname()[1];http=None;thread=None
            try:
                http,url=launcher.prepare(port)
                self.assertNotEqual(http.server_port,port)
                self.assertTrue(url.endswith('/?login=1'))
                thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
                with urlopen(url.split('/?')[0]+'/presentation.html') as response:
                    self.assertEqual(response.status,200)
                    self.assertIn(b'location.origin',response.read())
                reused,same=launcher.prepare(port)
                self.assertIsNone(reused);self.assertEqual(url,same)
            finally:
                if http:
                    if thread:http.shutdown();thread.join()
                    http.server_close()
                blocker.close();launcher.server.DATA=old

if __name__=='__main__':unittest.main()
