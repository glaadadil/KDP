"""Restore offline into a NEW directory. Never overwrite an active catalogue."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from zipfile import ZipFile

def restore(archive,destination):
    dest=Path(destination).resolve()
    if dest.exists(): raise ValueError("Choisis un nouveau dossier de destination.")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as folder:
        stage=Path(folder)/"restauration"
        (stage/"originals").mkdir(parents=True)
        with ZipFile(archive) as z:
            names=z.namelist()
            if len(set(names))!=len(names) or "catalogue.sqlite3" not in names:
                raise ValueError("Archive de sauvegarde invalide.")
            for item in z.infolist():
                n=item.filename
                if n!="catalogue.sqlite3" and not re.fullmatch(r"originals/[a-f0-9]{64}",n): raise ValueError("Entrée de sauvegarde invalide.")
                with z.open(item) as inp,(stage/n).open("xb") as out:
                    shutil.copyfileobj(inp,out)
                if n.startswith("originals/"):
                    with (stage/n).open("rb") as inp:
                        if hashlib.file_digest(inp,"sha256").hexdigest()!=n.split("/")[1]: raise ValueError("Original altéré.")
        c=sqlite3.connect(stage/"catalogue.sqlite3")
        try:
            c.execute("PRAGMA trusted_schema=OFF")
            if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("Catalogue endommagé.")
            for (s,) in c.execute("SELECT snapshot FROM history UNION ALL SELECT body FROM projects"):
                for f in json.loads(s)["files"]:
                    if not re.fullmatch(r"[a-f0-9]{64}",f["sha256"]) or not (stage/"originals"/f["sha256"]).is_file():
                        raise ValueError("Original manquant.")
        finally: c.close()
        if dest.exists(): raise ValueError("La destination existe déjà.")
        stage.rename(dest)
    return dest
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("sauvegarde")
    p.add_argument("destination")
    args=p.parse_args()
    try: print("Restauration terminée :",restore(args.sauvegarde,args.destination))
    except (ValueError,OSError,sqlite3.Error) as exc: p.exit(1,str(exc)+"\n")
