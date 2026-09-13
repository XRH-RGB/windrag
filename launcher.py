"""Open login reliably: reuse matching instance or allocate a free local port."""
import argparse, json, threading, webbrowser
from urllib.request import build_opener, ProxyHandler
import server

def matching_instance(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:
            value=json.load(response)
        return value.get('application')=='windrag' and value.get('instance')==server.instance_identity() and value.get('build')==server.build_identity()
    except Exception:return False

def prepare(preferred=8770):
    state=server.DATA/'last_port.txt'
    try:previous=int(state.read_text().strip())
    except (OSError,ValueError):previous=preferred
    for port in dict.fromkeys([previous,preferred]):
        if 1<=port<=65535 and matching_instance(port):return None,f'http://127.0.0.1:{port}/?login=1'
    try:http=server.ThreadingHTTPServer(('127.0.0.1',preferred),server.Handler)
    except OSError:http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    server.init_db()
    state.write_text(str(http.server_port),encoding='ascii')
    return http,f'http://127.0.0.1:{http.server_port}/?login=1'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--report',action='store_true');parser.add_argument('--port',type=int,default=8770);args=parser.parse_args()
    try:http,url=prepare(args.port)
    except Exception as e:
        print('Unable to start WindRAG: '+str(e));return 1
    print('Login: '+url,flush=True)
    # Persist the actual address, including fallback ports, beside this launcher's data.
    (server.DATA/'系统登录地址.txt').write_text(url+'\n',encoding='utf-8')
    (server.ROOT/'打开运行中的系统.url').write_text('[InternetShortcut]\nURL='+url+'\n',encoding='utf-8')
    print('Demo accounts: admin / admin123; operator / operator123; user / user123',flush=True)
    print('Existing changed passwords are preserved. Engineer / librarian: Wind@2026!',flush=True)
    if not args.no_browser:
        # Delay only the browser opening; the HTTP loop can start immediately.
        timer=threading.Timer(.4,lambda:webbrowser.open(url.split('/?')[0]+'/presentation.html' if args.report else url));timer.daemon=True;timer.start()
    if http is None:
        print('Reusing the running instance.',flush=True)
        if not args.no_browser:timer.join(2)
        return 0
    print('Keep this window open. Ctrl+C stops the service.',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close()
    return 0

if __name__=='__main__':raise SystemExit(main())
