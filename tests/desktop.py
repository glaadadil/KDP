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
            mission = page.evaluate("navigator.clipboard.readText()")
            assert "Readers who keep field journals." in mission
            # Use the identifiers from the actual copied prompt, as ChatGPT would.
            envelope = None
            decoder = json.JSONDecoder()
            for pos, character in enumerate(mission):
                if character != "{":
                    continue
                try:
                    candidate, _ = decoder.raw_decode(mission[pos:])
                except json.JSONDecodeError:
                    continue
                if isinstance(candidate, dict) and candidate.get("protocol") == "venture.stage.v1" and candidate.get("stage") == "Recherche":
                    envelope = candidate
                    break
            assert envelope is not None, "The copied mission must include a valid response template."
            evidence = {
                "protocol": envelope["protocol"],
                "edition_id": envelope["edition_id"],
                "stage": envelope["stage"],
                "deliverable": "A sample card under 90 mm fits the intended pocket.",
                "handoff": "Base the next prototype on a 90 mm maximum width.",
                "decisions": [], "sources": [], "checks": [], "open_questions": [],
                "suggested_metadata": {"subtitle": "Notes from the trail"},
            }
            page.locator("#import-stage").click()
            page.locator("#stage-reply").fill("A free-form note that should stay in this dialog.")
            page.locator("#preview-stage-reply").click()
            expect(page.locator("#dialog-note")).to_be_visible()
            expect(page.locator("#save-stage-reply")).to_have_count(0)
            page.locator("#stage-reply").fill(json.dumps(evidence))
            page.locator("#preview-stage-reply").click()
            expect(page.get_by_role("dialog")).to_contain_text(evidence["handoff"])
            page.locator("#save-stage-reply").click()
            expect(page.get_by_role("dialog")).not_to_be_visible()
            expect(page.get_by_label("Résultat du spécialiste")).to_have_value(evidence["deliverable"])
            expect(page.locator("#content .tag").first).to_have_text("À valider")
            page.reload()
            expect(page.get_by_label("Résultat du spécialiste")).to_have_value(evidence["deliverable"])
            page.get_by_role("button",name="Valider l’étape").click()
            expect(page.get_by_role("heading",name="Conception",exact=True)).to_be_visible()
            page.get_by_text("Spécialité des missions", exact=True).click()
            page.locator("#workshop-kind").select_option("imprimable")
            page.locator("#apply-workshop-kind").click()
            expect(page.locator("#content .upper")).to_contain_text("Imprimable")
            page.get_by_role("button",name="Copier la mission").click()
            expect(page.locator("#toast")).to_contain_text("Mission copiée")
            next_mission = page.evaluate("navigator.clipboard.readText()")
            assert evidence["handoff"] in next_mission and "activité pilote" in next_mission
            page.locator('[data-step="1"]').click()
            page.locator('#proposal-fields input[value="subtitle"]').check()
            page.locator("#apply-proposals").click()
            expect(page.locator("#proposal-fields input")).to_be_disabled()
            page.get_by_role("button", name="Fiche produit", exact=True).click()
            expect(page.get_by_label("Sous-titre", exact=True)).to_have_value(evidence["suggested_metadata"]["subtitle"])
            page.get_by_role("button",name="Bibliothèque Venture Publisher").click()
            page.get_by_role("button",name="Importer une fiche",exact=True).click()
            page.locator("#jsonfile").set_input_files(ROOT/"examples/paper/produit.json")
            page.get_by_role("button",name="Importer le manifeste").click()
            expect(page.get_by_role("heading",name="Fichiers de l’édition")).to_be_visible()
            page.locator("#browse").set_input_files(ROOT/"examples/paper/interior.pdf")
            expect(page.get_by_text("interior.pdf",exact=True)).to_be_visible()
            page.get_by_role("button",name="Aperçu",exact=True).first.click()
            expect(page.get_by_alt_text("Page 1 du PDF")).to_be_visible()
            with page.expect_response(lambda r:r.url.endswith("/page/2")) as rendered:
                page.get_by_role("button",name="Page suivante").click()
            assert rendered.value.ok and rendered.value.body().startswith(b"\x89PNG")
            expect(page.get_by_alt_text("Page 2 du PDF")).to_be_visible()
            page.get_by_role("button",name="Fermer",exact=True).click()
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
        print("PASS • projet, mission copiée, import ChatGPT, validation humaine, passation, fiche produit, fichiers, trois exports, confirmation, historique et sauvegarde.")
    finally:
        server.terminate()
        server.wait(12)
