"""Bootstrap a private virtual environment, then start the loopback application."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

HERE=Path(__file__).resolve().parent
def run():
    parser=argparse.ArgumentParser(description="Venture Publisher")
    parser.add_argument("--no-browser",action="store_true")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--installed",action="store_true",help="Utiliser l'environnement Python actif")
    args=parser.parse_args()
    if sys.version_info<(3,11):
        sys.exit("Installe Python 3.11 ou plus récent.")
    if not args.installed:
        env=HERE/".venv"
        exe=env/("Scripts/python.exe" if os.name=="nt" else "bin/python")
        if not exe.is_file(): venv.EnvBuilder(with_pip=True).create(env)
        requirements=HERE/"requirements.txt"
        fingerprint=hashlib.sha256(requirements.read_bytes()).hexdigest()
        stamp=env/"venture-install.txt"
        if not stamp.exists() or stamp.read_text()!=fingerprint:
            subprocess.run([str(exe),"-m","pip","install","-r",str(requirements)],check=True)
            stamp.write_text(fingerprint)
        args2=[str(exe),str(Path(__file__).resolve()),"--installed","--port",str(args.port)]
        if args.no_browser: args2.append("--no-browser")
        sys.exit(subprocess.call(args2,cwd=HERE))
    import uvicorn
    from venture.app import app
    url=f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        def open_when_ready():
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(50):
                try:
                    with opener.open(url+"/api/config",timeout=.4) as r:
                        if b'"stages"' in r.read():
                            webbrowser.open(url)
                            return
                except OSError: pass
                time.sleep(.15)
        threading.Thread(target=open_when_ready,daemon=True).start()
    print("Venture Publisher • "+url,flush=True)
    uvicorn.run(app,host="127.0.0.1",port=args.port,access_log=False)
if __name__=="__main__": run()
