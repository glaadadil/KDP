import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import httpx
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from venture.app import app
from venture import etsy, quality
from restaurer import restore

EX=Path(__file__).resolve().parents[1]/"examples"
def pdf(width=432,height=648,count=24):
    out=io.BytesIO()
    writer=PdfWriter()
    for _ in range(count):writer.add_blank_page(width,height)
    writer.write(out)
    return out.getvalue()

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{"VP_DATA":self.tmp.name})
        self.env.start()
        self.c=TestClient(app,headers={"X-Venture-Action":"local"})
        self.c.__enter__()
    def tearDown(self):
        self.c.__exit__(None,None,None)
        self.env.stop()
        self.tmp.cleanup()
    def demo(self,ch="paper"):
        r=self.c.post("/api/demo/"+ch)
        self.assertEqual(r.status_code,200,r.text)
        self.p=r.json();self.base="/api/projects/"+self.p["id"]
    def refresh(self):self.p=self.c.get(self.base).json()
    def request(self,method,endpoint="",**kw):
        return self.c.request(method,self.base+endpoint,headers={"If-Match":str(self.p["rev"])},**kw)
    def report(self):return self.c.get(self.base+"/checks").json()
    def upload(self,name,b,role="pending"):
        r=self.request("POST","/files",files={"files":(name,b)},data={"role":role})
        self.assertEqual(r.status_code,200,r.text);self.p=r.json()
    def bad(self):return [r["text"] for r in self.report() if r["level"]=="error"]
    def ready(self):
        r=self.request("POST","/export")
        self.assertEqual(r.status_code,200,r.text[:200] if r.status_code!=200 else "")
        self.refresh()
        return r.content
    def test_valid_pdf_and_original(self):
        self.demo()
        self.assertEqual(self.bad(),[])
        f=self.p["files"][0]
        self.assertEqual(f["info"]["pages"],24)
        self.assertEqual(self.c.get(self.base+"/files/"+f["id"]).content,(EX/"paper/interior.pdf").read_bytes())
    def test_corrupt_pdf_and_version_history(self):
        self.demo();self.upload("interior.pdf",b"%PDF-not-valid","interior")
        self.assertTrue(any("illisible" in s for s in self.bad()))
        self.assertEqual(self.request("POST","/export").status_code,409)
        self.assertEqual(len(self.p["files"]),3)
        self.assertFalse(self.p["files"][0]["active"])
    def test_missing_cover(self):
        self.demo();f=self.p["files"][1]
        self.assertEqual(self.request("DELETE","/files/"+f["id"]).status_code,200)
        self.assertTrue(any("Couverture PDF" in s for s in self.bad()))
    def test_page_dimensions_and_mixed_sizes(self):
        self.demo();self.upload("interior.pdf",pdf(612,792),"interior")
        self.assertTrue(any("attendu" in s for s in self.bad()))
    def test_etsy_limits(self):
        self.demo("etsy");self.upload("large.txt",b"a"*20_000_001,"client")
        self.assertTrue(any("20 Mo" in s for s in self.bad()))
        for i in range(4):self.upload(f"note-{i}.txt",b"Note","client")
        self.assertTrue(any("5 fichiers" in s for s in self.bad()))
    def test_manifest_validation_and_external_claims(self):
        m=json.loads((EX/"paper/produit.json").read_text())
        m["declared_validations"]=["ready"]
        r=self.c.post("/api/projects",json=m);self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()["status"],"Brouillon")
        self.assertEqual(self.c.post("/api/projects",json=m).status_code,409)
        for change in [{"schema_version":"2.0"},{"expected":[{"name":"../x.pdf","role":"client"}]},{"expected":m["expected"]*2},{"surprise":True},{"price":-1}]:
            self.assertEqual(self.c.post("/api/projects",json=m|change).status_code,422,change)
    def test_persistence_after_restart(self):
        self.demo()
        with TestClient(app) as other:self.assertEqual(other.get(self.base).json(),self.p)
    def test_exports_all_channels_and_manual_confirmation(self):
        for ch in ("paper","etsy","kindle"):
            with self.subTest(ch=ch):
                self.demo(ch);out=self.ready()
                with ZipFile(io.BytesIO(out)) as z:
                    self.assertIn("fiche-commerciale.txt",z.namelist());self.assertIn("produit.json",z.namelist())
                    self.assertIn("depot-et-controles.txt",z.namelist());self.assertIsNone(z.testzip())
                self.assertEqual(self.p["status"],"Prêt au dépôt")
                old=self.p["rev"];self.ready();self.assertEqual(old,self.p["rev"])
                self.assertEqual(self.request("POST","/status",json={"state":"Publié","confirmed":True}).status_code,422)
                r=self.request("POST","/status",json={"state":"Publié","reference":"EXAMPLE-ONLY","confirmed":True})
                self.assertEqual(r.json()["status"],"Publié")
    def test_validation_revisions_and_concurrent_changes(self):
        self.demo();current=self.p["rev"]
        r=self.request("PUT","/stages/0",json={"text":"Approved reader profile.","decision":"approve"})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.request("PUT",json=self.p["manifest"]).status_code,409)
        self.refresh()
        self.assertIn("Approved reader profile.",self.c.get(self.base+"/mission/1").json()["text"])
        self.assertEqual(self.request("PUT","/stages/1",json={"text":"Sources","decision":"approve"}).status_code,200)
        self.refresh();self.assertEqual(self.request("PUT","/stages/0",json={"text":"Changed audience","decision":"approve"}).json()["stages"][1]["status"],"review")
        self.assertEqual(self.c.get(self.base+f"/history/{current}").json()["stages"][0]["text"],"")
    def test_bundle_and_duplicate(self):
        self.demo("etsy");out=self.ready()
        with tempfile.TemporaryDirectory() as base,patch.dict(os.environ,{"VP_DATA":base}):
            with TestClient(app,headers={"X-Venture-Action":"local"}) as other:
                res=other.post("/api/bundle",files={"archive":("product.zip",out)})
                self.assertEqual(res.status_code,200,res.text)
                report=other.get("/api/projects/"+res.json()["id"]+"/checks").json()
                self.assertFalse(any(r["level"]=="error" for r in report))
                self.assertEqual(other.post("/api/bundle",files={"archive":("again.zip",out)}).status_code,409)
    def test_edition_isolation_and_duplicates(self):
        self.demo();self.ready()
        data={"version":"2","channel":"etsy"}
        r=self.request("POST","/edition",json=data)
        self.assertEqual(r.json()["status"],"Brouillon");self.assertEqual(r.json()["files"][0]["role"],"pending")
        self.assertEqual(self.request("POST","/edition",json=data).status_code,409)
        self.assertEqual(self.c.get(self.base).json()["files"][0]["role"],"interior")
    def test_backup_and_restore(self):
        self.demo("etsy");self.ready()
        r=self.c.post("/api/backup");self.assertEqual(r.status_code,200)
        backup=Path(self.tmp.name)/"save.zip";backup.write_bytes(r.content)
        target=Path(self.tmp.name)/"restored";restore(backup,target)
        with self.assertRaises(ValueError):restore(backup,target)
        with patch.dict(os.environ,{"VP_DATA":str(target)}):
            self.assertEqual(self.c.get(self.base).json(),self.p)
            self.assertEqual(self.bad(),[])
    def test_no_cross_origin_mutation(self):
        with TestClient(app) as c:
            self.assertEqual(c.post("/api/demo/paper").status_code,403)
            self.assertEqual(c.get("/api/config",headers={"Host":"third-party.invalid"}).status_code,400)
    def test_integrity_before_export(self):
        self.demo("etsy");f=self.p["files"][0]
        (Path(self.tmp.name)/"originals"/f["sha256"]).write_bytes(b"changed")
        self.assertEqual(self.request("POST","/export").status_code,409)
    def test_mock_etsy_operations_and_idempotency(self):
        self.demo("etsy");self.ready();calls=[]
        def handler(req):
            calls.append((req.method,req.url.path))
            if req.method=="GET":return httpx.Response(200,json={"currency_code":"USD"})
            if req.method=="PATCH":return httpx.Response(200,json={"listing_id":10,"state":"active"})
            if req.url.path.endswith("/files"):return httpx.Response(200,json={"listing_file_id":99})
            if req.url.path.endswith("/images"):return httpx.Response(200,json={"listing_image_id":97})
            return httpx.Response(201,json={"listing_id":10})
        g=etsy.Etsy(httpx.Client(transport=httpx.MockTransport(handler)))
        g.settings=["key","test-secret","https://localhost/return","9"]
        g.session={"access":"test","refresh":"test","until":float("inf")}
        with patch.object(etsy,"gateway",g):
            payload={"taxonomy":1,"when":"2020_2026","confirmed":True}
            r=self.request("POST","/etsy/draft",json=payload)
            self.assertEqual(r.status_code,200,r.text);self.refresh()
            self.assertEqual(self.p["status"],"Dépôt en cours")
            self.assertEqual(self.request("POST","/etsy/draft",json=payload).status_code,200);self.refresh()
            self.assertEqual(sum(m=="POST" for m,path in calls),3)
            self.assertEqual(self.request("POST","/etsy/publish",json={"confirmed":False}).status_code,422)
            self.assertEqual(self.request("POST","/etsy/publish",json={"confirmed":True}).json()["status"],"Publié")
            self.refresh();self.assertEqual(self.request("POST","/etsy/publish",json={"confirmed":True}).status_code,409)
            self.assertEqual(sum(m=="PATCH" for m,path in calls),1)
    def test_timeout_does_not_duplicate_and_reconcile(self):
        self.demo("etsy");self.ready();mutations=[]
        def handler(req):
            if req.method=="GET":return httpx.Response(200,json={"currency_code":"USD","shop_id":9,"state":"draft","title":self.p["manifest"]["title"]})
            mutations.append(req.method);raise httpx.ReadTimeout("timed out",request=req)
        g=etsy.Etsy(httpx.Client(transport=httpx.MockTransport(handler)))
        g.settings=["key","test-secret","https://localhost/return","9"];g.session={"access":"test","until":float("inf")}
        with patch.object(etsy,"gateway",g):
            payload={"taxonomy":1,"when":"2020_2026","confirmed":True}
            self.assertEqual(self.request("POST","/etsy/draft",json=payload).status_code,502);self.refresh()
            self.assertNotEqual(self.p["status"],"Publié")
            self.assertEqual(self.request("POST","/etsy/draft",json=payload).status_code,409);self.refresh()
            self.assertEqual(mutations,["POST"])
            r=self.request("POST","/etsy-reconcile",json={"op":"listing","remote_id":"15","confirmed":True})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(self.c.get(self.base+"/etsy-pending").json(),[])
    def test_oauth_pkce_and_state(self):
        from urllib.parse import urlparse,parse_qs
        g=etsy.Etsy(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={"access_token":"a","refresh_token":"r","expires_in":3600}))))
        g.settings=["k","s","https://localhost/back","1"]
        with patch.object(etsy,"gateway",g):
            url=self.c.post("/api/etsy/connect",json={"confirmed":True}).json()["url"]
            params=parse_qs(urlparse(url).query);self.assertEqual(params["code_challenge_method"],["S256"])
            self.assertEqual(self.c.post("/api/etsy/return",json={"url":"https://localhost/back?code=c&state=wrong"}).status_code,400)
            r=self.c.post("/api/etsy/return",json={"url":"https://localhost/back?code=c&state="+params["state"][0]})
            self.assertTrue(r.json()["connected"]);self.assertNotIn("refresh",r.text)

    def test_tool_customer_zip_and_dashboard_summary(self):
        self.demo("outil")
        self.assertEqual(self.p["manifest"]["kind"],"outil")
        with ZipFile(io.BytesIO(self.ready())) as z:
            name="client/event-budget.xlsx.zip"
            self.assertIn(name,z.namelist())
            with ZipFile(io.BytesIO(z.read(name))) as package:
                with ZipFile(io.BytesIO(package.read("event-budget.xlsx"))) as workbook:
                    self.assertIn(b"SUM(B5:B9)",workbook.read("xl/worksheets/sheet1.xml"))
        self.upload("broken.pdf",b"broken","client")
        listed=self.c.get("/api/projects").json()
        self.assertGreater(listed[0]["blocking_count"],0)

    def test_originals_survive_failed_batch_and_duplicate_retry(self):
        self.demo("paper")
        data=pdf()
        r=self.request("POST","/files",files=[("files",("good.pdf",data)),("files",("bad.xyz",b"abc"))])
        self.assertEqual(r.status_code,422);self.refresh();self.assertEqual(len(self.p["files"]),2)
        self.upload("extra.pdf",data,"source");rev=self.p["rev"]
        self.upload("extra.pdf",data,"source");self.assertEqual(self.p["rev"],rev)
        with ZipFile(io.BytesIO(self.ready())) as z:self.assertFalse(any("extra" in f for f in z.namelist()))

    def test_archive_entry_and_undeclared_inputs(self):
        for name in ("../bad.txt","C:evil.txt"):
            output=io.BytesIO()
            with ZipFile(output,"w") as z:
                z.writestr("produit.json",(EX/"etsy"/"produit.json").read_bytes())
                z.writestr(name,b"bad")
            self.assertEqual(self.c.post("/api/bundle",files={"archive":("file.zip",output.getvalue())}).status_code,422)
