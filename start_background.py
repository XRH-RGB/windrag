"""Start the local service independently, verify readiness, then open the browser."""
import argparse, os, subprocess, sys, time, webbrowser
from pathlib import Path
import launcher

def start(open_browser=True):
    root=Path(__file__).resolve().parent
    data=launcher.server.DATA
    data.mkdir(parents=True,exist_ok=True)
    try:previous=int((data/'last_port.txt').read_text().strip())
    except (OSError,ValueError):previous=8770
    for port in dict.fromkeys([previous,8770]):
        if 1<=port<=65535 and launcher.matching_instance(port):
            url=f'http://127.0.0.1:{port}/?login=1'
            if open_browser:webbrowser.open(url)
            return url
    log=data/'service.log'
    env=os.environ.copy();env['WINDRAG_DATA']=str(data.resolve());env['PYTHONIOENCODING']='utf-8'
    with log.open('ab',buffering=0) as output:
        kwargs=dict(cwd=str(root),env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=output,close_fds=True)
        if os.name=='nt':
            kwargs['creationflags']=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_BREAKAWAY_FROM_JOB
        else:kwargs['start_new_session']=True
        process=subprocess.Popen([sys.executable,str(root/'launcher.py'),'--no-browser','--port','8770'],**kwargs)
    (data/'service.pid').write_text(str(process.pid),encoding='ascii')
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError(f'Service stopped. See {log}')
        try:
            port=int((data/'last_port.txt').read_text().strip())
            if launcher.matching_instance(port):
                url=f'http://127.0.0.1:{port}/?login=1'
                if open_browser:webbrowser.open(url)
                return url
        except (OSError,ValueError):pass
        time.sleep(.25)
    raise RuntimeError(f'Service not ready. See {log}')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--report',action='store_true');args=parser.parse_args()
    try:
        url=start(not args.no_browser and not args.report)
        if args.report:
            report_url=url.split('/?')[0]+'/presentation.html'
            if not args.no_browser:webbrowser.open(report_url)
            print(report_url,flush=True)
        else:print(url,flush=True)
    except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
