"""Etsy Open API v3. Authentication is ephemeral, operations are journalled in SQLite."""
import base64
import hashlib
import os
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import httpx
from fastapi import HTTPException
from .quality import PACK, wrapped, delivery_name, rows
from .store import db, get, original, save

LOCK=threading.RLock()
API="https://openapi.etsy.com/v3/application"
TOKEN="https://api.etsy.com/v3/public/oauth/token"
class Etsy:
    def __init__(self,client=None):
        self.client=client or httpx.Client(timeout=45,follow_redirects=False,trust_env=False)
        self.session={}
        self.pending={}
        self.settings=None

    def config(self):
        return self.settings or [os.environ.get(k,"").strip() for k in ("VP_ETSY_KEY","VP_ETSY_SECRET","VP_ETSY_REDIRECT","VP_ETSY_SHOP")]

    def state(self):
        key,secret,redirect,shop=self.config()
        valid=bool(key and secret and redirect and shop.isdigit())
        return {"configured":valid,"connected":bool(self.session),"shop":shop if valid else ""}

    def begin(self):
        if not self.state()["configured"]: raise HTTPException(400,"Configure les quatre paramètres Etsy indiqués dans le guide.")
        key,_,redirect,_=self.config()
        dest=urlsplit(redirect)
        if dest.scheme!="https" or dest.hostname not in ("localhost","127.0.0.1") or dest.query or dest.fragment:
            raise HTTPException(400,"L'URI de retour enregistrée doit être HTTPS sur localhost ou 127.0.0.1 sans paramètres.")
        state=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(48)
        self.pending=dict(state=state,verifier=verifier,until=time.monotonic()+600)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        return "https://www.etsy.com/oauth/connect?"+urlencode(dict(response_type="code",client_id=key,redirect_uri=redirect,scope="listings_r listings_w shops_r",state=state,code_challenge=challenge,code_challenge_method="S256"))

    def token(self,data):
        try:
            response=self.client.post(TOKEN,data=data)
            response.raise_for_status()
            payload=response.json()
            self.session=dict(access=payload["access_token"],refresh=payload["refresh_token"],until=time.monotonic()+max(0,int(payload["expires_in"])-60))
        except (httpx.HTTPError,ValueError,KeyError):
            raise HTTPException(502,"Échange OAuth impossible. Vérifie les paramètres ou reconnecte Etsy.")

    def complete(self,url):
        key,_,redirect,_=self.config()
        parts=urlsplit(url)
        q=parse_qs(parts.query)
        pending=self.pending
        if not pending or time.monotonic()>pending["until"] or url.split("?")[0]!=redirect or not secrets.compare_digest(q.get("state",[""])[0],pending["state"]) or not q.get("code"):
            raise HTTPException(400,"Retour OAuth invalide, expiré ou refusé.")
        self.pending={}
        self.token(dict(grant_type="authorization_code",client_id=key,redirect_uri=redirect,code=q["code"][0],code_verifier=pending["verifier"]))

    def request(self,method,path,**options):
        key,secret,_,shop=self.config()
        if not self.session: raise HTTPException(401,"Connecte d'abord ta boutique.")
        if time.monotonic()>=self.session["until"]:
            self.token(dict(grant_type="refresh_token",client_id=key,refresh_token=self.session["refresh"]))
        headers={"x-api-key":key+":"+secret,"Authorization":"Bearer "+self.session["access"]}
        try:
            r=self.client.request(method,API+path,headers=headers,**options)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(502,f"Etsy a répondu HTTP {e.response.status_code}. Vérifie la boutique et l'historique avant de reprendre.")
        except (httpx.HTTPError,ValueError):
            raise HTTPException(502,"Réponse Etsy non confirmée. Vérifie l'état dans la boutique avant de reprendre.")

gateway=Etsy()

def existing(pid,op):
    with db() as c:
        row=c.execute("SELECT state,result FROM remote_ops WHERE project=? AND op=?",(pid,op)).fetchone()
        return tuple(row) if row else None

def once(pid,op,send):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row=c.execute("SELECT state,result FROM remote_ops WHERE project=? AND op=?",(pid,op)).fetchone()
        if row:
            if row["state"]=="done": return row["result"]
            raise HTTPException(409,"Une requête Etsy reste non confirmée. Rapproche son résultat depuis la boutique avant une reprise.")
        c.execute("INSERT INTO remote_ops VALUES(?,?,'pending','')",(pid,op))
    result=str(send())
    with db() as c: c.execute("UPDATE remote_ops SET state='done',result=? WHERE project=? AND op=?",(result,pid,op))
    return result

def draft(p,taxonomy,when):
    m=p["manifest"]
    shop=gateway.config()[3]
    if m["channel"]!="etsy" or not p["export_fingerprint"] or any(r["level"]=="error" for r in rows(p)):
        raise HTTPException(409,"Prépare d'abord un dossier Etsy valide.")
    if not gateway.state()["connected"]: raise HTTPException(401,"Connecte la boutique.")
    shop_data=gateway.request("GET",f"/shops/{shop}")
    if shop_data.get("currency_code")!=m["currency"]:
        raise HTTPException(409,"La devise du produit diffère de celle de la boutique.")
    base=f"/shops/{shop}/listings"
    data=dict(quantity=999,title=m["title"],description=m["description"],price=str(m["price"]),taxonomy_id=taxonomy,who_made="i_did",when_made=when,type="download")
    if m["keywords"]: data["tags"]=",".join(m["keywords"])
    listing=once(p["id"],"listing",lambda:gateway.request("POST",base,data=data)["listing_id"])
    for f in p["files"]:
        if not f["active"] or f["role"] not in ("client","notice","preview"): continue
        image=f["role"]=="preview"
        def upload():
            endpoint=base+f"/{listing}/"+("images" if image else "files")
            filename=f["name"] if image else delivery_name(f)
            with original(f).open("rb") as src:
                body=wrapped(f) if not image and f["info"]["ext"] in PACK else src
                resp=gateway.request("POST",endpoint,data={} if image else {"name":filename},files={("image" if image else "file"):(filename,body)})
            return resp["listing_image_id" if image else "listing_file_id"]
        once(p["id"],"upload/"+f["id"],upload)
    return listing

def live(p):
    op=existing(p["id"],"listing")
    if not op or op[0]!="done" or p["status"]!="Dépôt en cours": raise HTTPException(409,"Un brouillon Etsy complet est requis.")
    listing=op[1]
    if p["reference"]!="https://www.etsy.com/listing/"+listing: raise HTTPException(409,"Termine le transfert du brouillon avant activation.")
    for f in p["files"]:
        if f["active"] and f["role"] in ("preview","client","notice"):
            uploaded=existing(p["id"],"upload/"+f["id"])
            if not uploaded or uploaded[0]!="done": raise HTTPException(409,"Transfert incomplet.")
    shop=gateway.config()[3]
    def activate():
        res=gateway.request("PATCH",f"/shops/{shop}/listings/{listing}",data={"state":"active"})
        if res.get("state")!="active" or str(res.get("listing_id"))!=listing:
            raise HTTPException(502,"Activation non confirmée par Etsy.")
        return listing
    once(p["id"],"activate",activate)
    return listing

def pending_ops(pid):
    with db() as c: return [r[0] for r in c.execute("SELECT op FROM remote_ops WHERE project=? AND state='pending'",(pid,))]

def reconcile(p,op,remote_id,absent):
    """A delayed POST is never blindly repeated. Confirm absence, or verify a specific remote resource."""
    pid=p["id"]
    if op not in pending_ops(pid): raise HTTPException(409,"Aucune opération en attente pour cette action.")
    if absent:
        if op=="activate": raise HTTPException(409,"Vérifie d'abord l'état distant de l'annonce pour reprendre une activation.")
        with db() as c: c.execute("DELETE FROM remote_ops WHERE project=? AND op=? AND state='pending'",(pid,op))
        return "Absence confirmée dans la boutique. Reprise autorisée."
    shop=gateway.config()[3]
    if op=="listing":
        if not remote_id.isdigit(): raise HTTPException(422,"Indique l'identifiant du brouillon constaté.")
        listing=gateway.request("GET",f"/listings/{remote_id}")
        if (str(listing.get("shop_id"))!=shop or listing.get("state")!="draft" or listing.get("title")!=p["manifest"]["title"]):
            raise HTTPException(409,"Le brouillon distant ne correspond pas à cette édition.")
    else:
        listing_id=existing(pid,"listing")[1]
        if op=="activate":
            listing=gateway.request("GET",f"/listings/{listing_id}")
            if str(listing.get("shop_id"))!=shop:raise HTTPException(409,"Boutique différente.")
            if listing.get("state")=="draft":
                with db() as c: c.execute("DELETE FROM remote_ops WHERE project=? AND op=? AND state='pending'",(pid,op))
                return "Etsy confirme que l’annonce est encore au brouillon."
            if listing.get("state")!="active":raise HTTPException(409,"Activation encore indéterminée.")
            remote_id=listing_id
        elif op.startswith("upload/"):
            f=next((f for f in p["files"] if "upload/"+f["id"]==op),None)
            if not f or not remote_id.isdigit():raise HTTPException(422,"Fichier ou identifiant invalide.")
            image=f["role"]=="preview"
            path=f"/listings/{listing_id}/images/{remote_id}" if image else f"/shops/{shop}/listings/{listing_id}/files/{remote_id}"
            resource=gateway.request("GET",path)
            if str(resource.get("listing_image_id" if image else "listing_file_id"))!=remote_id:
                raise HTTPException(409,"Ressource distante différente.")
            if not image and resource.get("filename")!=delivery_name(f):raise HTTPException(409,"Nom de fichier distant différent.")
    with db() as c: c.execute("UPDATE remote_ops SET state='done',result=? WHERE project=? AND op=? AND state='pending'",(remote_id,pid,op))
    return "Réponse rapprochée avec la boutique."
