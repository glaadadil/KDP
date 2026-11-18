import hashlib
import math
import re
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
from io import BytesIO
from xml.etree import ElementTree
from PIL import Image
from pypdf import PdfReader
from .store import original

LEVELS=("ok","warning","error","human")
SOURCE_ETSY="https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings"
SOURCE_KDP="https://kdp.amazon.com/en_US/help/topic/GVBQ3CMEQW3W2VL6"
SOURCE_COVER="https://kdp.amazon.com/en_US/help/topic/G201953020"
PACK={".xlsx",".ods",".csv",".docx",".md"}
def inspect_fonts(resources,seen):
    faults=set()
    if not resources: return faults
    res=resources.get_object()
    for ref in res.get("/Font",{}).get_object().values() if "/Font" in res else []:
        font=ref.get_object()
        if font.get("/Subtype")=="/Type3": continue
        faces=font.get("/DescendantFonts",[font])
        for entry in faces:
            face=entry.get_object()
            desc=face.get("/FontDescriptor")
            if not desc or not any(k in desc.get_object() for k in ("/FontFile","/FontFile2","/FontFile3")):
                faults.add(str(face.get("/BaseFont","police inconnue")))
    for ref in res["/XObject"].get_object().values() if "/XObject" in res else []:
        obj=ref.get_object()
        marker=id(obj)
        if obj.get("/Subtype")=="/Form" and marker not in seen:
            seen.add(marker)
            faults.update(inspect_fonts(obj.get("/Resources"),seen))
    return faults

def inspect(path,name):
    ext=Path(name).suffix.lower()
    info={"ext":ext}
    try:
        if ext==".pdf":
            with path.open("rb") as src:
                if not src.read(5)==b"%PDF-": raise ValueError()
                src.seek(0)
                pdf=PdfReader(src)
                if pdf.is_encrypted: raise ValueError()
                sizes=set()
                fonts=set()
                boxes_differ=False
                for page in pdf.pages:
                    unit=float(page.get("/UserUnit",1))
                    w,h=[float(n)*unit/72 for n in (page.mediabox.width,page.mediabox.height)]
                    if page.rotation%180: w,h=h,w
                    if not all(math.isfinite(n) and n>0 for n in (w,h)): raise ValueError()
                    sizes.add((round(w,4),round(h,4)))
                    boxes_differ |= list(page.cropbox)!=list(page.mediabox)
                    fonts.update(inspect_fonts(page.get("/Resources"),set()))
                if not sizes: raise ValueError()
                info.update(pages=len(pdf.pages),sizes=sorted(sizes),unembedded=sorted(fonts),boxes_differ=boxes_differ)
        elif ext in (".png",".jpg",".jpeg"):
            with Image.open(path) as im:
                if im.format!=("PNG" if ext==".png" else "JPEG"): raise ValueError()
                info["pixels"]=im.size
                info["color_mode"]=im.mode
                im.verify()
            with Image.open(path) as im: im.load()
        elif ext in (".zip",".epub",".docx",".xlsx",".ods"):
            with ZipFile(path) as z:
                members=z.infolist()
                if len(members)>12000 or sum(i.file_size for i in members)>800_000_000:
                    raise ValueError()
                for i in members:
                    parts=PurePosixPath(i.filename)
                    if parts.is_absolute() or ".." in parts.parts or '\\' in i.filename or ":" in i.filename or i.flag_bits&1: raise ValueError()
                if not any(not i.is_dir() for i in members) or z.testzip(): raise ValueError()
                if ext==".epub":
                    if z.read("mimetype")!=b"application/epub+zip": raise ValueError()
                    doc=ElementTree.fromstring(z.read("META-INF/container.xml"))
                    opf=doc.find(".//{*}rootfile").attrib["full-path"]
                    package=ElementTree.fromstring(z.read(opf))
                    if package.find(".//{*}spine/{*}itemref") is None: raise ValueError()
                if ext==".xlsx" and "xl/workbook.xml" not in z.namelist(): raise ValueError()
                if ext==".docx" and "word/document.xml" not in z.namelist(): raise ValueError()
                if ext==".ods" and z.read("mimetype")!=b"application/vnd.oasis.opendocument.spreadsheet": raise ValueError()
                info["entries"]=len(members)
        else:
            with path.open(encoding="utf-8-sig") as src:
                for line in src:
                    if "\x00" in line: raise ValueError()
        if not path.stat().st_size: raise ValueError()
    except Exception:
        info["error"]="Fichier illisible, protégé, endommagé ou incompatible avec son extension."
    return info

def rows(project):
    m=project["manifest"]
    channel=m["channel"]
    files=[f for f in project["files"] if f["active"]]
    result=[]
    def add(level,msg): result.append({"level":level,"text":msg})
    for field,label in [("description","description"),("category","catégorie"),("price","prix"),("author","auteur ou marque")]:
        if not m[field]: add("error","Complète la fiche : "+label+".")
    if m["ai"]=="unknown" or m["ai"]=="generated" and not m["ai_details"]:
        add("error","Précise l'utilisation de l'IA dans la fiche.")
    if not m["keywords"]: add("warning","Aucun mot-clé renseigné.")
    if len(m["keywords"])>(13 if channel=="etsy" else 7): add("error","Trop de mots-clés pour ce canal.")
    if channel=="etsy" and (len(m["title"])>140 or any(len(k)>20 for k in m["keywords"])):
        add("error","Etsy : titre limité à 140 caractères et tags à 20 caractères.")
    if channel!="etsy" and len(m["title"])+len(m["subtitle"])>200: add("error","Titre et sous-titre dépassent 200 caractères.")
    active={f["name"].casefold():f for f in files}
    for e in m["expected"]:
        f=active.get(e["name"].casefold())
        if not f or f["role"]!=e["role"]: add("error","Fichier attendu absent ou rôle incorrect : "+e["name"])
    digests={}
    for f in files:
        if f["sha256"] in digests:
            add("warning","Contenu identique sous deux noms : "+digests[f["sha256"]]+" et "+f["name"])
        digests[f["sha256"]]=f["name"]
        if not original(f).is_file(): add("error","Original introuvable : "+f["name"])
        if f["role"]=="pending": add("error","Confirme le rôle de "+f["name"])
        if f["info"].get("error"): add("error",f["name"]+" • "+f["info"]["error"])
        if f["role"]!="source" and f["role"] not in channel_roles(channel): add("error","Rôle incompatible avec cette destination : "+f["name"])
    if channel=="etsy":
        etsy_checks(files,add)
    elif channel=="paper":
        paper_checks(m,files,add)
    else:
        manuscript=required(files,"ebook",{".epub"},"Manuscrit Kindle EPUB",add)
        cover=required(files,"cover",{".jpg",".jpeg"},"Couverture Kindle JPEG",add)
        if cover and "pixels" in cover["info"]:
            w,h=cover["info"]["pixels"]
            if cover["info"].get("color_mode")=="CMYK": add("error","Convertis la couverture Kindle en RVB.")
            if h<2500: add("warning","Pour une couverture Kindle plus nette, vise au moins 2 500 pixels de hauteur.")
            if w>=h: add("warning","Vérifie l'orientation de la couverture Kindle.")
        if manuscript: add("human","Parcours l'EPUB dans Kindle Previewer, y compris la navigation et les illustrations.")
    add("human","Valide les droits, la déclaration IA, la catégorie et le rendu. Vérifie les prix, frais ou redevances dans la plateforme.")
    if not any(r["level"]=="error" for r in result): add("ok","Contrôles automatiques réussis pour les fichiers et paramètres fournis.")
    return result

def channel_roles(channel):
    return {"etsy":{"client","notice","preview"},"paper":{"interior","cover"},"kindle":{"ebook","cover"}}[channel]

def required(files,role,exts,label,add):
    found=[f for f in files if f["role"]==role]
    if len(found)!=1 or found[0]["info"]["ext"] not in exts:
        add("error",f"{label} : un fichier requis ({', '.join(sorted(exts))}).")
        return None
    return found[0]

def etsy_checks(files,add):
    client=[f for f in files if f["role"] in ("client","notice")]
    if not 1<=len(client)<=5: add("error","Etsy requiert de 1 à 5 fichiers client, notices comprises.")
    names=set()
    for f in client:
        name=delivery_name(f)
        if name.casefold() in names: add("error","Deux fichiers ont le même nom de livraison : "+name)
        names.add(name.casefold())
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,70}",name): add("error","Renomme le fichier client (70 caractères maximum, lettres ASCII, chiffres, point, tiret ou souligné) : "+name)
        if f["size"]>20_000_000 and f["info"]["ext"] not in PACK: add("error","Fichier client de plus de 20 Mo : "+name)
        if f["info"]["ext"] in PACK and original(f).exists():
            if len(wrapped(f))>20_000_000: add("error","Archive client supérieure à 20 Mo : "+name)
    previews=[f for f in files if f["role"]=="preview"]
    if not previews: add("error","Ajoute une image de présentation.")
    if any(f["info"]["ext"] not in (".png",".jpeg",".jpg") for f in previews): add("error","Les aperçus doivent être des images PNG ou JPEG.")

def delivery_name(f):
    return f["name"]+".zip" if f["info"]["ext"] in PACK else f["name"]

def wrapped(f):
    buf=BytesIO()
    with ZipFile(buf,"w",ZIP_DEFLATED) as z: z.write(original(f),f["name"])
    return buf.getvalue()

def paper_checks(m,files,add):
    interior=required(files,"interior",{".pdf"},"Intérieur PDF",add)
    cover=required(files,"cover",{".pdf"},"Couverture PDF complète",add)
    opt=m["print"]
    w,h=map(float,opt["trim"].split("x"))
    bleed=opt["bleed"]
    def match(f,width,height):
        for size in f["info"].get("sizes",[]):
            if abs(size[0]-width)>0.006 or abs(size[1]-height)>0.006:
                add("error",f"{f['name']} : {size[0]:g} × {size[1]:g} po ; attendu {width:.4f} × {height:.4f} po.")
                break
        if f["info"].get("unembedded"): add("error","Polices non incorporées dans "+f["name"]+" : "+", ".join(f["info"]["unembedded"]))
        if f["info"].get("boxes_differ"): add("human","Les zones de rognage et de support diffèrent. Vérifie-les dans Print Previewer.")
    if interior and "pages" in interior["info"]:
        match(interior,w+(0.125 if bleed else 0),h+(0.25 if bleed else 0))
        pages=interior["info"]["pages"]
        count=pages+pages%2
        paper=opt["paper"]
        low,high,spine={"white":(24,828,.002252),"cream":(24,776,.0025),"premium-color":(24,828,.002347),"standard-color":(72,600,.002252)}[paper]
        if not low<=count<=high: add("error",f"Pagination hors plage pour ce papier ({low} à {high} pages).")
        if cover: match(cover,2*w+count*spine+.25,h+.25)
    if cover and cover["info"].get("pages",1)!=1: add("error","La couverture complète doit occuper une seule page.")
    add("human","Vérifie les marges intérieures, le fond perdu du contenu, la tranche et le code-barres dans KDP Print Previewer.")
