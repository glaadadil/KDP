"""End-to-end browser exercise on a fresh temporary catalogue and an actual local HTTP server."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from zipfile import ZipFile
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    origin=f"http://127.0.0.1:{port}"
    cmd=[sys.executable,str(ROOT/"lancer.py"),"--installed","--no-browser","--port",str(port)]
    server=subprocess.Popen(cmd,env={**os.environ,"VP_DATA":folder},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            try:
                with opener.open(origin+"/api/config",timeout=.4):break
            except OSError:time.sleep(.1)
        with sync_playwright() as driver:
            browser=driver.chromium.launch(executable_path=os.environ.get("VP_CHROMIUM") or shutil.which("chromium"),args=["--no-sandbox"])
            ctx=browser.new_context(viewport={"width":1440,"height":960},accept_downloads=True,permissions=["clipboard-read","clipboard-write"])
            page=ctx.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.set_default_timeout(8500)
            page.goto(origin);expect(page.get_by_role("heading",name="Bibliothèque",exact=True)).to_be_visible()
            page.get_by_role("button",name="Nouveau projet").click()
            page.get_by_label("Titre du produit").fill("Guide des observations")
            page.get_by_role("button",name="Créer le projet").click()
            page.get_by_label("Résultat du spécialiste").fill("Readers who keep field journals.")
            page.reload()
            expect(page.get_by_label("Résultat du spécialiste")).to_have_value("Readers who keep field journals.")
            page.get_by_role("button",name="Valider l’étape").click()
            expect(page.get_by_role("heading",name="Recherche")).to_be_visible()
            page.get_by_role("button",name="Copier la mission").click()
            expect(page.locator("#toast")).to_contain_text("Mission copiée")
            assert "Readers who keep field journals." in page.evaluate("navigator.clipboard.readText()")
            page.get_by_role("button",name="Bibliothèque Venture Publisher").click()
            page.get_by_role("button",name="Importer une fiche",exact=True).click()
            page.locator("#jsonfile").set_input_files(ROOT/"examples/paper/produit.json")
            page.get_by_role("button",name="Importer le manifeste").click()
            expect(page.get_by_role("heading",name="Fichiers de l’édition")).to_be_visible()
            page.locator("#browse").set_input_files(ROOT/"examples/paper/interior.pdf")
            expect(page.get_by_text("interior.pdf",exact=True)).to_be_visible()
            page.get_by_role("button",name="Contrôler le dossier").click()
            expect(page.locator(".check.error").first).to_be_visible()
            page.get_by_role("button",name="Gérer les fichiers").click()
            page.locator("#browse").set_input_files(ROOT/"examples/paper/cover.pdf")
            expect(page.get_by_text("cover.pdf",exact=True)).to_be_visible()
            page.get_by_role("button",name="Contrôler le dossier").click()
            expect(page.locator(".check.ok")).to_be_visible()
            page.get_by_role("button",name="Préparer le dépôt").click()
            with page.expect_download() as dl: page.get_by_role("button",name="Télécharger le dossier ZIP").click()
            with ZipFile(dl.value.path()) as z: assert set(["couverture/cover.pdf","interieur/interior.pdf","produit.json"])<=set(z.namelist())
            page.get_by_role("button",name="Confirmer un statut").click()
            page.get_by_label("Statut observé").select_option("Publié")
            page.get_by_label("Référence, ASIN ou lien").fill("TEST-LOCAL")
            page.get_by_role("button",name="Confirmer le statut observé").click()
            expect(page.locator(".splithead .tag")).to_have_text("Publié")
            page.get_by_role("button",name="Historique",exact=True).click()
            expect(page.get_by_text("Confirmation manuelle • Publié")).to_be_visible()
            page.get_by_role("button",name="Bibliothèque Venture Publisher").click()
            page.get_by_role("button",name="Ouvrir un exemple complet").click()
            page.get_by_role("button",name="Etsy numérique",exact=True).click()
            expect(page.locator(".check.ok")).to_be_visible()
            page.get_by_role("button",name="Préparer le dépôt").click()
            with page.expect_download() as dl: page.get_by_role("button",name="Télécharger le dossier ZIP").click()
            with ZipFile(dl.value.path()) as z:assert "client/field-record.pdf" in z.namelist()
            page.get_by_role("button",name="Bibliothèque Venture Publisher").click()
            page.get_by_role("button",name="Ouvrir un exemple complet").click()
            page.get_by_role("button",name="Kindle eBook",exact=True).click()
            expect(page.locator(".check.ok")).to_be_visible()
            page.get_by_role("button",name="Préparer le dépôt").click()
            with page.expect_download() as dl: page.get_by_role("button",name="Télécharger le dossier ZIP").click()
            with ZipFile(dl.value.path()) as z:assert "manuscrit/field-notes.epub" in z.namelist()
            with page.expect_download() as dl: page.get_by_role("button",name="Sauvegarder",exact=True).click()
            with ZipFile(dl.value.path()) as z:assert "catalogue.sqlite3" in z.namelist()
            page.get_by_role("button",name="Bibliothèque Venture Publisher").click()
            expect(page.get_by_text("Mes éditions",exact=True)).to_be_visible()
            if os.environ.get("VP_SCREENSHOT"):page.screenshot(path=os.environ["VP_SCREENSHOT"],full_page=True)
            assert not errors,errors
            browser.close()
        print("PASS • projet, brouillon après rechargement, mission copiée, manifeste, import, erreur et correction, trois exports, confirmation, historique et sauvegarde.")
    finally:
        server.terminate()
        server.wait(12)
