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
            if ch == "etsy":
                # Plain-text stages reproduce a completed edition from an earlier installation.
                for index in range(8):
                    text = f"Approved field guide content for stage {index}."
                    approval = Request(
                        endpoint + f"/stages/{index}",
                        data=json.dumps({"decision": "approve", "text": text}).encode(),
                        method="PUT",
                        headers={**headers, "Content-Type": "application/json", "If-Match": str(project["rev"])},
                    )
                    with opener.open(approval) as r:
                        project = json.load(r)
                with opener.open(endpoint + "/delivery") as r:
                    delivery = json.load(r)
                    assert delivery["approved"] and delivery["next"] == "deposit"
                    assert "fichiers téléchargeables" in delivery["prompt"]
                with opener.open(endpoint + "/delivery/manuscript") as r:
                    assert r.read().decode() == project["stages"][5]["text"]
                with opener.open(endpoint + "/delivery/dossier") as r:
                    dossier = r.read().decode()
                    assert all(stage["text"] in dossier for stage in project["stages"])
            if ch=="paper":
                with opener.open(endpoint+"/mission/0") as r:
                    mission = json.load(r)
                packet = mission["template"]
                assert '"edition_id": "' + project["id"] + '"' in mission["text"]
                packet.update(
                    deliverable="Produce a field guide for walkers. Include two worked examples.",
                    handoff="Collect the sources needed for two worked examples.",
                )
                response = json.dumps(packet)
                json_headers = {**headers, "Content-Type": "application/json"}
                preview = Request(endpoint+"/stages/0/preview", data=json.dumps({"response": response}).encode(), headers=json_headers)
                with opener.open(preview) as r:
                    assert json.load(r)["handoff"]==packet["handoff"]
                incoming = {"decision": "draft", "response": response}
                request = Request(
                    endpoint+"/stages/0", data=json.dumps(incoming).encode(), method="PUT",
                    headers={**json_headers, "If-Match": str(project["rev"])},
                )
                with opener.open(request) as r:
                    project = json.load(r)
                    assert project["stages"][0]["status"] == "review"
                url=endpoint+"/files/"+project["files"][0]["id"]+"/page/1"
                with opener.open(url) as r: assert r.read(4)==b"\x89PNG"
            with opener.open(endpoint+"/checks") as r:assert not any(x["level"]=="error" for x in json.load(r))
            with opener.open(Request(endpoint+"/export",method="POST",headers={**headers,"If-Match":str(project["rev"])})) as r:assert r.read(4)==b"PK\x03\x04"
        print("Portable Windows : lancement et quatre dossiers de dépôt vérifiés.")
    finally:
        p.terminate()
        p.wait(20)
