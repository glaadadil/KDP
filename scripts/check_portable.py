"""Exercise the shipped Windows binary with no dependencies from the source tree."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener, ProxyHandler, Request

exe=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as s:
        s.bind(("127.0.0.1",0))
        port=s.getsockname()[1]
    base=f"http://127.0.0.1:{port}"
    opener=build_opener(ProxyHandler({}))
    p=subprocess.Popen([str(exe),"--no-browser","--port",str(port)],cwd=temp,env={**os.environ,"VP_DATA":temp})
    try:
        for _ in range(100):
            if p.poll() is not None:raise RuntimeError("Le lanceur s’est arrêté.")
            try:
                with opener.open(base+"/api/config",timeout=.5) as r:
                    assert len(json.load(r)["stages"])==8
                break
            except OSError:time.sleep(.3)
        else:raise RuntimeError("Démarrage trop long.")
        headers={"X-Venture-Action":"local"}
        for ch in ("etsy","paper","kindle","outil"):
            with opener.open(Request(base+"/api/demo/"+ch,method="POST",headers=headers)) as r:project=json.load(r)
            endpoint=base+"/api/projects/"+project["id"]
            with opener.open(endpoint+"/checks") as r:assert not any(x["level"]=="error" for x in json.load(r))
            with opener.open(Request(endpoint+"/export",method="POST",headers={**headers,"If-Match":str(project["rev"])})) as r:assert r.read(4)==b"PK\x03\x04"
        print("Portable Windows : lancement et quatre dossiers de dépôt vérifiés.")
    finally:
        p.terminate()
        p.wait(20)
