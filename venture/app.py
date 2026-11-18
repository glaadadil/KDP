import hashlib
import json
import mimetypes
import os
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from zipfile import ZIP_DEFLATED, ZipFile
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field, ValidationError
from . import etsy, quality, store
from .models import *
from .workshop import STAGES, complete_context, mission
from .stage_reply import ApplySuggestions, RawStageReply, WorkshopKind, parse_reply, reply_template

BASE=Path(__file__).resolve().parent
@asynccontextmanager
async def lifespan(app):
    store.init()
    yield
app=FastAPI(title="Venture Publisher",lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["localhost","127.0.0.1","[::1]","testserver"])
@app.middleware("http")
async def protect(request,call_next):
    if request.method not in ("GET","HEAD") and request.headers.get("x-venture-action")!="local":
        return JSONResponse({"detail":"Cette action doit provenir de l'application locale."},403)
    response=await call_next(request)
    response.headers.update({"X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer","X-Frame-Options":"SAMEORIGIN","Cache-Control":"no-store"})
    if request.url.path=="/":
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'self'"
    return response

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    fields=[".".join(str(part) for part in e["loc"][1:])+" • "+e["msg"] for e in exc.errors()[:5]]
    return JSONResponse({"detail":"Données invalides : "+" | ".join(fields)},422)

def revision(if_match:str):
    try: return int(if_match)
    except ValueError: raise HTTPException(400,"Révision de projet manquante.")

def editable(p):
    if etsy.existing(p["id"],"listing"): raise HTTPException(409,"Un brouillon Etsy est associé à cette édition. Duplique l'édition pour la modifier.")
    store.invalidate(p)

def tempfile_path():
    fd,name=tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    return Path(name)

def deliver(path,name):
    return FileResponse(path,filename=name,media_type="application/zip",background=BackgroundTask(path.unlink,missing_ok=True))

@app.get("/")
def home(): return FileResponse(BASE/"web"/"index.html")

@app.get("/api/config")
def config():
    return dict(stages=[s[0] for s in STAGES],roles=ROLES,channels=CHANNELS,etsy=etsy.gateway.state())

@app.get("/api/schema")
def schema(): return Manifest.model_json_schema()

@app.get("/api/projects")
def library():
    with store.db() as c:
        out=[]
        for row in c.execute("SELECT body FROM projects ORDER BY json_extract(body,'$.updated') DESC,rowid DESC"):
            p=json.loads(row[0])
            out.append(dict(id=p["id"],manifest={k:p["manifest"][k] for k in ("title","kind","version","channel","product_id")},status=p["status"],updated=p["updated"],blocking_count=p.get("blocking_count",0),progress=sum(s["status"]=="approved" for s in p["stages"]),review=any(s["status"]=="review" for s in p["stages"]),files=sum(f["active"] for f in p["files"])))
        return out

@app.post("/api/projects")
def create(m:Manifest):
    with store.db() as c: return store.save(c,store.make(m.model_dump()),"Projet créé")

@app.get("/api/projects/{pid}")
def read(pid:str):
    with store.db() as c: return store.get(c,pid)

@app.put("/api/projects/{pid}")
def edit(pid:str,m:Manifest,if_match:str=Header()):
    with store.change(pid,revision(if_match)) as (c,p):
        old=p["manifest"]
        if any(old[k]!=getattr(m,k) for k in ("product_id","kind","version","channel")):
            raise HTTPException(409,"Pour changer d'édition ou de canal, duplique le projet.")
        editable(p)
        if any(old[k]!=getattr(m,k) for k in ("brief","language")):
            for stage in p["stages"]:
                if stage["status"]=="approved": stage["status"]="review"
        p["manifest"]=m.model_dump()
        return store.save(c,p,"Fiche mise à jour")

@app.post("/api/projects/{pid}/edition")
def edition(pid:str,new:Edition):
    with store.db() as c:
        p=store.get(c,pid)
        m={**p["manifest"],**new.model_dump()}
        copy=store.make(m)
        if p.get("workshop_kind"):
            copy["workshop_kind"] = p["workshop_kind"]
        copy["files"]=p["files"]
        copy["stages"]=p["stages"]
        if m["channel"]!=p["manifest"]["channel"]:
            m["expected"]=[]
            for stage in copy["stages"]:
                if stage["status"]=="approved": stage["status"]="review"
            for f in copy["files"]:
                if f["role"]!="source": f["role"]="pending"
        return store.save(c,copy,"Édition dérivée de "+p["manifest"]["version"])

def attach(p,name,stream,role):
    try: filename(name)
    except ValueError as e: raise HTTPException(422,str(e))
    if Path(name).suffix.lower() not in ALLOWED: raise HTTPException(422,"Format non pris en charge : "+name)
    digest,size=store.stash(stream)
    prior=[f for f in p["files"] if f["active"] and f["name"].casefold()==name.casefold()]
    if prior and prior[0]["sha256"]==digest: return False
    for f in prior: f["active"]=False
    expected=next((e["role"] for e in p["manifest"]["expected"] if e["name"].casefold()==name.casefold()),None)
    f=dict(id=uid(),name=name,role=role if role!="pending" else expected or "pending",sha256=digest,size=size,active=True)
    f["info"]=quality.inspect(store.original(f),name)
    p["files"].append(f)
    return True

@app.post("/api/projects/{pid}/files")
def add_files(pid:str,files:list[UploadFile]=File(),role:Role=Form("pending"),if_match:str=Header()):
    with store.change(pid,revision(if_match)) as (c,p):
        if not 1<=len(files)<=80: raise HTTPException(422,"Importe entre 1 et 80 fichiers à la fois.")
        editable(p)
        changed=False
        for f in files:
            changed=attach(p,f.filename or "",f.file,role) or changed
        return store.save(c,p,"Fichiers importés ; originaux conservés") if changed else store.get(c,pid)

def find_file(p,fid):
    for f in p["files"]:
        if f["id"]==fid: return f
    raise HTTPException(404,"Fichier introuvable.")

@app.get("/api/projects/{pid}/files/{fid}")
def download(pid:str,fid:str,inline:bool=False):
    f=find_file(read(pid),fid)
    ext=f["info"]["ext"]
    preview=inline and ext in {".png",".jpg",".jpeg",".pdf"}
    path=store.original(f)
    if not path.is_file(): raise HTTPException(404,"Original manquant.")
    return FileResponse(path,filename=f["name"],media_type=mimetypes.guess_type(f["name"])[0] or "application/octet-stream",content_disposition_type="inline" if preview else "attachment",headers={"Content-Security-Policy":"sandbox; default-src 'none'"})

@app.patch("/api/projects/{pid}/files/{fid}")
def file_role(pid:str,fid:str,change:RoleChange,if_match:str=Header()):
    with store.change(pid,revision(if_match)) as (c,p):
        editable(p)
        f=find_file(p,fid)
        f["role"]=change.role
        return store.save(c,p,"Rôle confirmé • "+f["name"])

@app.delete("/api/projects/{pid}/files/{fid}")
def archive(pid:str,fid:str,if_match:str=Header()):
    with store.change(pid,revision(if_match)) as (c,p):
        editable(p)
        f=find_file(p,fid)
        f["active"]=False
        return store.save(c,p,"Fichier retiré de l'édition • "+f["name"])

def stage_name(index):
    if not 0 <= index < len(STAGES):
        raise HTTPException(404, "Étape inconnue.")
    return STAGES[index][0]


def validate_reply(text, pid, name):
    try:
        return parse_reply(text, pid, name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/projects/{pid}/workshop-kind")
def change_workshop_kind(pid: str, body: WorkshopKind, if_match: str = Header()):
    with store.change(pid, revision(if_match)) as (c, project):
        if project.get("workshop_kind") == body.kind:
            return project
        project["workshop_kind"] = body.kind
        effective = body.kind or project["manifest"]["kind"]
        return store.save(c, project, "Spécialité des missions modifiée • " + effective)


@app.get("/api/projects/{pid}/mission/{index}")
def get_mission(pid: str, index: int, convert: bool = False, include_current: bool = True):
    name = stage_name(index)
    project = read(pid)
    return {
        "text": mission(project, index, convert=convert, include_current=include_current),
        "template": reply_template(pid, name),
    }


@app.get("/api/projects/{pid}/mission/{index}/context")
def mission_context(pid: str, index: int):
    stage_name(index)
    return PlainTextResponse(
        complete_context(read(pid), index),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="contexte-etape-{index+1}.md"'},
    )


@app.post("/api/projects/{pid}/stages/{index}/preview")
def preview_reply(pid: str, index: int, body: RawStageReply):
    name = stage_name(index)
    read(pid)
    return validate_reply(body.response, pid, name)


@app.put("/api/projects/{pid}/stages/{index}")
def stage(pid: str, index: int, body: Result, if_match: str = Header()):
    name = stage_name(index)
    with store.change(pid, revision(if_match)) as (c, project):
        previous = project["stages"][index]
        if body.response is not None:
            if body.decision != "draft" or body.text:
                raise HTTPException(422, "Importe une réponse seule pour relecture. La validation est une action distincte.")
            packet = validate_reply(body.response, pid, name)
            text = packet["deliverable"]
        else:
            text = body.text
            # A changed free-text deliverable no longer matches the original machine handoff.
            # Its exact earlier packet remains in the revision history.
            packet = previous.get("packet") if previous["text"] == text else None
        if body.decision == "approve":
            if not text:
                raise HTTPException(422, "Ajoute le livrable avant validation.")
            if any(s["status"] != "approved" for s in project["stages"][:index]):
                raise HTTPException(409, "Valide les étapes précédentes avant celle-ci.")
        elif body.decision == "revise" and not body.notes:
            raise HTTPException(422, "Indique la correction demandée.")
        state = {"approve": "approved", "revise": "revise", "draft": "review"}[body.decision]
        notes = previous["notes"] if body.response is not None and "notes" not in body.model_fields_set else body.notes
        next_stage = {"text": text, "notes": notes, "status": state}
        if packet is not None:
            next_stage["packet"] = packet
        if previous == next_stage:
            return project
        for later in project["stages"][index+1:]:
            if later["status"] == "approved":
                later["status"] = "review"
        project["stages"][index] = next_stage
        message = (
            "réponse structurée importée pour relecture" if body.response is not None
            else {"approved": "validé", "review": "enregistré", "revise": "correction demandée"}[state]
        )
        return store.save(c, project, f"{name} • {message}")


@app.post("/api/projects/{pid}/stages/{index}/apply-metadata")
def apply_stage_metadata(pid: str, index: int, body: ApplySuggestions, if_match: str = Header()):
    name = stage_name(index)
    with store.change(pid, revision(if_match)) as (c, project):
        packet = project["stages"][index].get("packet") or {}
        proposed = packet.get("suggested_metadata", {})
        if not set(body.fields).issubset(proposed):
            raise HTTPException(422, "Sélectionne uniquement des champs proposés dans la réponse importée.")
        edited = dict(project["manifest"])
        edited.update({key: proposed[key] for key in body.fields})
        try:
            updated = Manifest.model_validate(edited).model_dump()
        except ValidationError as exc:
            raise HTTPException(422, "Les valeurs sélectionnées sont incompatibles avec la fiche produit.") from exc
        if project["manifest"] == updated:
            return project
        editable(project)
        project["manifest"] = updated
        return store.save(c, project, f"{name} • suggestions appliquées à la fiche : " + ", ".join(body.fields))


@app.get("/api/projects/{pid}/checks")
def checks(pid:str): return quality.rows(read(pid))

@app.get("/api/projects/{pid}/history")
def history(pid:str):
    with store.db() as c:
        store.get(c,pid)
        return [dict(row) for row in c.execute("SELECT rev,at,message FROM history WHERE project=? ORDER BY rev DESC",(pid,))]

@app.get("/api/projects/{pid}/history/{rev}")
def snapshot(pid:str,rev:int):
    with store.db() as c:
        item=c.execute("SELECT snapshot FROM history WHERE project=? AND rev=?",(pid,rev)).fetchone()
        if not item: raise HTTPException(404)
        return json.loads(item[0])

@app.post("/api/projects/{pid}/export")
def export(pid:str,if_match:str=Header()):
    path=tempfile_path()
    try:
        with store.change(pid,revision(if_match)) as (c,p):
            report=quality.rows(p)
            if any(r["level"]=="error" for r in report): raise HTTPException(409,"Corrige les contrôles bloquants avant l'export.")
            m=p["manifest"]
            manifest=Manifest.model_validate(m).model_dump()
            manifest["expected"]=[dict(name=quality.delivery_name(f) if m["channel"]=="etsy" and f["role"] in ("client","notice") else f["name"],role=f["role"]) for f in p["files"] if f["active"] and f["role"]!="source"]
            manifest["declared_checks"]=[r["level"]+" • "+r["text"] for r in report]
            manifest["declared_validations"]=[STAGES[i][0] for i,s in enumerate(p["stages"]) if s["status"]=="approved"]
            fingerprint=hashlib.sha256(json.dumps([m,[(f["role"],f["sha256"],f["name"]) for f in p["files"] if f["active"]]],sort_keys=True).encode()).hexdigest()
            instructions={
              "etsy":"Dans Etsy Shop Manager, créer une annonce numérique. Charger les fichiers client et les visuels depuis leurs dossiers respectifs. Vérifier catégorie, prix, devise, déclarations et frais avant activation.",
              "paper":"Dans la bibliothèque KDP, créer un livre broché. Reporter les métadonnées, paramètres, territoires et prix. Charger l'intérieur et la couverture complète. Contrôler le rendu dans Print Previewer et vérifier les redevances avant de soumettre.",
              "kindle":"Dans la bibliothèque KDP, créer un eBook Kindle. Charger l'EPUB et la couverture. Vérifier la navigation avec le prévisualiseur, la déclaration IA, les territoires, le prix et les redevances avant de soumettre."
            }[m["channel"]]
            with ZipFile(path,"w",ZIP_DEFLATED) as z:
                for f in p["files"]:
                    if not f["active"] or f["role"]=="source": continue
                    with store.original(f).open("rb") as source:
                        if hashlib.file_digest(source,"sha256").hexdigest()!=f["sha256"]: raise HTTPException(409,"Intégrité modifiée : "+f["name"])
                    folder={"preview":"visuels","client":"client","notice":"client","interior":"interieur","cover":"couverture","ebook":"manuscrit"}[f["role"]]
                    if m["channel"]=="etsy" and f["role"] in ("client","notice") and f["info"]["ext"] in quality.PACK:
                        z.writestr(folder+"/"+quality.delivery_name(f),quality.wrapped(f))
                    else: z.write(store.original(f),folder+"/"+f["name"])
                z.writestr("produit.json",json.dumps(manifest,indent=2,ensure_ascii=False))
                z.writestr("fiche-commerciale.txt","\n\n".join(f"{k}\n{v}" for k,v in [
                 ("Titre",m["title"]),("Sous-titre",m["subtitle"]),("Auteur ou marque",m["author"]),("Langue",m["language"]),("Description",m["description"]),("Mots-clés",", ".join(m["keywords"])),("Catégorie",m["category"]),("Prix",f"{m['price']} {m['currency']}"),("IA",m["ai"]+" "+m["ai_details"]),("Édition",m["version"])]))
                z.writestr("depot-et-controles.txt",instructions+"\n\n"+"\n".join(r["level"].upper()+" • "+r["text"] for r in report))
            if p["export_fingerprint"]!=fingerprint or p["status"]=="Correction nécessaire":
                p["export_fingerprint"]=fingerprint
                p["status"]="Prêt au dépôt"
                store.save(c,p,"Dossier de dépôt préparé")
        return deliver(path,"Venture-"+m["channel"]+"-"+fingerprint[:10]+".zip")
    except BaseException:
        path.unlink(missing_ok=True)
        raise

@app.post("/api/projects/{pid}/status")
def set_status(pid:str,body:Publication,if_match:str=Header()):
    with store.change(pid,revision(if_match)) as (c,p):
        if not p["export_fingerprint"]: raise HTTPException(409,"Prépare le dossier avant d'enregistrer un dépôt.")
        if body.state=="Publié" and not body.reference: raise HTTPException(422,"Saisis la référence confirmée par la plateforme.")
        if p["status"]==body.state and p["reference"]==body.reference: return p
        p.update(status=body.state,reference=body.reference)
        return store.save(c,p,"Confirmation manuelle • "+body.state)

@app.post("/api/backup")
def backup():
    path=tempfile_path()
    try: store.backup(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return deliver(path,"Venture-sauvegarde-"+store.now()[:10]+".zip")

@app.post("/api/demo/{channel}")
def demo(channel:Literal["etsy","paper","kindle","outil"]):
    source=BASE.parent/"examples"/channel
    m=Manifest.model_validate_json((source/"produit.json").read_text(encoding="utf-8")).model_dump()
    m["product_id"]=uid()
    p=store.make(m)
    for e in m["expected"]:
        with (source/e["name"]).open("rb") as stream: attach(p,e["name"],stream,e["role"])
    with store.db() as c: return store.save(c,p,"Exemple importé")

class UrlInput(Strict):
    url:str=Field(max_length=4096)
class DraftParams(Strict):
    taxonomy:int=Field(gt=0)
    when:str=Field(pattern=r"^(?:[0-9]{4}_[0-9]{4}|before_[0-9]{4})$")
    confirmed:Literal[True]
class Confirm(Strict):
    confirmed:Literal[True]
@app.post("/api/etsy/connect")
def connect(body:Confirm):
    with etsy.LOCK: return {"url":etsy.gateway.begin()}
@app.post("/api/etsy/return")
def returned(body:UrlInput):
    with etsy.LOCK: etsy.gateway.complete(body.url)
    return etsy.gateway.state()
@app.post("/api/etsy/disconnect")
def disconnect():
    with etsy.LOCK:
        etsy.gateway.session={}
        etsy.gateway.pending={}
        etsy.gateway.settings=None
    return etsy.gateway.state()

@app.post("/api/projects/{pid}/etsy/{action}")
def etsy_action(pid:str,action:Literal["draft","publish"],params:DraftParams|Confirm,if_match:str=Header()):
    with etsy.LOCK:
        p=read(pid)
        if p["rev"]!=revision(if_match): raise HTTPException(409,"Recharge le projet.")
        if action=="draft":
            if not etsy.gateway.state()["connected"]: raise HTTPException(401,"Connecte d’abord la boutique.")
            if not isinstance(params,DraftParams): raise HTTPException(422,"Catégorie et période requises.")
            if p["status"] not in ("Prêt au dépôt","Dépôt en cours"): raise HTTPException(409,"Le dossier doit être prêt au dépôt.")
            with store.change(pid,p["rev"]) as (c,p):
                p["status"]="Dépôt en cours"
                store.save(c,p,"Création du brouillon Etsy demandée")
            try:
                listing=etsy.draft(p,params.taxonomy,params.when)
            except HTTPException:
                if not etsy.existing(pid,"listing"):
                    with store.db() as c:
                        c.execute("BEGIN IMMEDIATE")
                        current=store.get(c,pid)
                        if current["status"]=="Dépôt en cours":
                            current["status"]="Prêt au dépôt"
                            store.save(c,current,"Brouillon non créé • paramètres à vérifier")
                raise
            state="Dépôt en cours"
        else:
            listing=etsy.live(p)
            state="Publié"
        with store.change(pid,p["rev"]) as (c,p):
            p.update(status=state,reference="https://www.etsy.com/listing/"+listing)
            return store.save(c,p,"Réponse Etsy confirmée • "+state)
app.mount("/assets",StaticFiles(directory=BASE/"web"),name="assets")

class Reconciliation(Strict):
    op:str=Field(max_length=100)
    remote_id:str=Field(default="",max_length=50)
    absent:bool=False
    confirmed:Literal[True]
@app.get("/api/projects/{pid}/etsy-pending")
def unresolved(pid:str):
    p=read(pid)
    result=[]
    for op in etsy.pending_ops(pid):
        label=next(("Transfert de "+f["name"] for f in p["files"] if op=="upload/"+f["id"]),{"listing":"Création du brouillon","activate":"Activation de l’annonce"}.get(op,op))
        result.append({"op":op,"label":label})
    return result
@app.post("/api/projects/{pid}/etsy-reconcile")
def reconcile(pid:str,body:Reconciliation,if_match:str=Header()):
    with etsy.LOCK:
        p=read(pid)
        if p["rev"]!=revision(if_match): raise HTTPException(409,"Recharge le projet.")
        message=etsy.reconcile(p,body.op,body.remote_id,body.absent)
        with store.change(pid,p["rev"]) as (c,p):
            if body.op=="activate" and etsy.existing(pid,"activate")==("done",p["reference"].split("/")[-1]):
                p["status"]="Publié"
            return store.save(c,p,message)

class SessionConfig(Strict):
    key:str=Field(min_length=1,max_length=200)
    secret:str=Field(min_length=1,max_length=300)
    shop:str=Field(pattern=r"^[0-9]{1,20}$")
    redirect:str=Field(max_length=300)
@app.post("/api/etsy/settings")
def settings(body:SessionConfig):
    from urllib.parse import urlsplit
    url=urlsplit(body.redirect)
    if url.hostname not in ("localhost","127.0.0.1") or url.scheme!="https" or url.query or url.fragment or url.username or url.password:
        raise HTTPException(422,"Indique le retour HTTPS local enregistré chez Etsy.")
    with etsy.LOCK:
        etsy.gateway.session={}
        etsy.gateway.pending={}
        etsy.gateway.settings=[body.key,body.secret,body.redirect,body.shop]
    return etsy.gateway.state()

@app.post("/api/bundle")
def import_bundle(archive:UploadFile=File()):
    import re
    from zipfile import BadZipFile
    from pydantic import ValidationError
    try:
        with ZipFile(archive.file) as z:
            items=z.infolist()
            if len(items)>150 or sum(x.file_size for x in items)>700_000_000:
                raise HTTPException(413,"Dossier trop volumineux.")
            paths={}
            for entry in items:
                parts=PurePosixPath(entry.filename)
                if parts.is_absolute() or ".." in parts.parts or "\\" in entry.filename or ":" in entry.filename or entry.flag_bits&1:
                    raise HTTPException(422,"Chemin ou chiffrement incompatible dans l'archive.")
                if entry.is_dir(): continue
                name=parts.name.casefold()
                if name in paths: raise HTTPException(422,"Nom ambigu dans le dossier : "+name)
                paths[name]=entry
            manifest=paths.get("produit.json")
            if not manifest or manifest.file_size>1_000_000: raise HTTPException(422,"Un manifeste produit.json valide est requis.")
            m=Manifest.model_validate_json(z.read(manifest)).model_dump()
            p=store.make(m)
            expected={e["name"].casefold():e["role"] for e in m["expected"]}
            for name,entry in paths.items():
                if name=="produit.json" or name in ("fiche-commerciale.txt","depot-et-controles.txt") and name not in expected: continue
                if Path(name).suffix not in ALLOWED: raise HTTPException(422,"Format inattendu dans le dossier : "+name)
                with z.open(entry) as stream: attach(p,PurePosixPath(entry.filename).name,stream,expected.get(name,"pending"))
            if len(p["files"])!=sum(f["active"] for f in p["files"]):raise HTTPException(422,"Noms incompatibles.")
            with store.db() as c: return store.save(c,p,"Manifeste et fichiers importés")
    except (BadZipFile,ValidationError,UnicodeError,ValueError,RuntimeError) as exc:
        raise HTTPException(422,"Archive ou manifeste invalide. Vérifie le format et les champs de produit.json.") from exc

@app.get("/api/projects/{pid}/files/{fid}/page/{number}")
def preview_page(pid:str,fid:str,number:int):
    from fastapi.responses import Response
    from .preview import pdf_page
    f=find_file(read(pid),fid)
    if f["info"]["ext"]!=".pdf" or not 1<=number<=f["info"].get("pages",0):
        raise HTTPException(404,"Page PDF introuvable.")
    try: png=pdf_page(store.original(f),number)
    except Exception: raise HTTPException(422,"Aperçu indisponible pour cette page. Télécharge l’original.")
    return Response(png,media_type="image/png")
