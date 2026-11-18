import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED
from fastapi import HTTPException
from .models import uid
from .workshop import STAGES

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def root():
    base=Path(os.environ.get("VP_DATA") or Path.home()/"VenturePublisher")
    base.mkdir(parents=True,exist_ok=True)
    (base/"originals").mkdir(exist_ok=True)
    return base

@contextmanager
def db():
    connection=sqlite3.connect(root()/"catalogue.sqlite3",timeout=30)
    connection.row_factory=sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def init():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, product TEXT, channel TEXT, edition TEXT, rev INTEGER, body TEXT, UNIQUE(product,channel,edition));
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, project TEXT, rev INTEGER, at TEXT, message TEXT, snapshot TEXT, UNIQUE(project,rev));
        CREATE TABLE IF NOT EXISTS remote_ops(project TEXT, op TEXT, state TEXT, result TEXT, PRIMARY KEY(project,op));
        """)

def get(c,pid):
    row=c.execute("SELECT body FROM projects WHERE id=?",(pid,)).fetchone()
    if not row: raise HTTPException(404,"Projet introuvable.")
    return json.loads(row[0])

def save(c,p,message):
    m=p["manifest"]
    p["rev"]+=1
    p["updated"]=now()
    body=json.dumps(p,ensure_ascii=False)
    try:
        c.execute("""INSERT INTO projects VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          product=excluded.product,channel=excluded.channel,edition=excluded.edition,rev=excluded.rev,body=excluded.body""",
          (p["id"],m["product_id"],m["channel"],m["version"],p["rev"],body))
    except sqlite3.IntegrityError:
        raise HTTPException(409,"Cette édition existe déjà pour ce produit et ce canal.")
    c.execute("INSERT INTO history(project,rev,at,message,snapshot) VALUES(?,?,?,?,?)",(p["id"],p["rev"],p["updated"],message,body))
    return p

def make(manifest):
    return dict(id=uid(),manifest=manifest,created=now(),rev=0,files=[],status="Brouillon",reference="",export_fingerprint="",stages=[
        dict(text="",notes="",status="open") for _ in STAGES])

@contextmanager
def change(pid,rev):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        p=get(c,pid)
        if p["rev"]!=rev:
            raise HTTPException(409,"Ce projet a changé dans un autre onglet. Recharge la page. Ton brouillon local reste disponible.")
        yield c,p

def invalidate(p):
    if p["status"] not in ("Brouillon","Correction nécessaire","Prêt au dépôt"):
        raise HTTPException(409,"Ce dossier est en dépôt. Crée une nouvelle édition pour modifier les fichiers ou la fiche.")
    p.update(status="Brouillon",reference="",export_fingerprint="")

def original(f):
    return root()/"originals"/f["sha256"]

def stash(stream):
    digest=hashlib.sha256()
    total=0
    with NamedTemporaryFile(dir=root()/"originals",prefix=".import-",delete=False) as out:
        tmp=Path(out.name)
        try:
            while block:=stream.read(1024*1024):
                total+=len(block)
                if total>650_000_000: raise HTTPException(413,"Limite locale de 650 Mo par fichier.")
                digest.update(block)
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            out.close()
            tmp.unlink(missing_ok=True)
            raise
    key=digest.hexdigest()
    dst=tmp.parent/key
    try:
        if not dst.exists(): os.replace(tmp,dst)
    finally:
        tmp.unlink(missing_ok=True)
    return key,total

def backup(path):
    with NamedTemporaryFile(delete=False) as tmp:
        snapshot=Path(tmp.name)
    try:
        with db() as c, sqlite3.connect(snapshot) as target:
            c.backup(target)
        with ZipFile(path,"w",ZIP_DEFLATED) as z, sqlite3.connect(snapshot) as image:
            z.write(snapshot,"catalogue.sqlite3")
            blobs=set()
            for body, in image.execute("SELECT snapshot FROM history"):
                blobs.update(f["sha256"] for f in json.loads(body)["files"])
            for sha in sorted(blobs):
                z.write(root()/"originals"/sha,"originals/"+sha)
    finally:
        snapshot.unlink(missing_ok=True)
