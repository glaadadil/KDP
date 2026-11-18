"""Round trips for specialist responses, including editions produced by the original workshop."""
import json
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from venture.app import app


class StageResponseTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"VP_DATA": directory}))
        self.client = self.enterContext(TestClient(app, headers={"X-Venture-Action": "local"}))
        created = self.client.post("/api/projects", json={
            "schema_version": "1.0", "kind": "imprimable", "channel": "etsy",
            "version": "1.0", "title": "Trail cards", "brief": "A pocket field note card.",
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.project = created.json()
        self.base = "/api/projects/" + self.project["id"]
        self.stages = self.client.get("/api/config").json()["stages"]

    def packet(self, index=0, **changes):
        return {
            "protocol": "venture.stage.v1",
            "edition_id": self.project["id"],
            "stage": self.stages[index],
            "deliverable": "One printable notebook card with a blank observation field.",
            "handoff": "Use a graphite-friendly pocket card.",
            "decisions": ["Reserve the lower half for a sketch."],
            "open_questions": ["Will a pencil smudge on the selected stock?"],
            "sources": ["Supplied project brief, section on materials."],
            "checks": ["Checked that the labels fit the proposed grid."],
            "suggested_metadata": {
                "title": "Pocket Field Cards",
                "keywords": ["field guide", "notebook"],
            },
            **changes,
        }

    def read(self):
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def send(self, method, suffix, data, revision=None):
        return self.client.request(
            method,
            self.base + suffix,
            headers={"If-Match": str(self.project["rev"] if revision is None else revision)},
            json=data,
        )

    def save_stage(self, index, data):
        response = self.send("PUT", f"/stages/{index}", data)
        self.assertEqual(response.status_code, 200, response.text)
        self.project = response.json()
        return self.project["stages"][index]

    def mission_data(self, index, suffix=""):
        response = self.client.get(f"{self.base}/mission/{index}{suffix}")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def preview(self, index, text):
        return self.send("POST", f"/stages/{index}/preview", {"response": text})

    def delivery(self):
        response = self.client.get(self.base + "/delivery")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_partial_legacy_edition_delivers_only_human_approved_material(self):
        untouched = self.read()
        state = self.delivery()
        self.assertEqual(state["next"], "workshop")
        self.assertEqual(state["approved_count"], 0)
        self.assertFalse(state["manuscript_available"])
        for route in ("manuscript", "dossier"):
            self.assertEqual(self.client.get(self.base + "/delivery/" + route).status_code, 409)
        self.assertEqual(self.read(), untouched)

        self.save_stage(0, {"text": "Carry two blank cards.", "notes": "Accepted note 17.", "decision": "approve"})
        self.save_stage(1, {"text": "DRAFT research claim 229", "decision": "draft"})
        before = self.read()
        self.assertEqual(self.delivery()["approved_count"], 1)
        partial = self.client.get(self.base + "/delivery/dossier")
        self.assertEqual(partial.status_code, 200)
        self.assertIn("attachment", partial.headers["content-disposition"])
        self.assertIn("Carry two blank cards.", partial.text)
        self.assertIn("Accepted note 17.", partial.text)
        self.assertNotIn("DRAFT research claim 229", partial.text)
        self.assertEqual(self.read(), before)

    def test_completed_workshop_hands_over_exact_manuscript_and_full_approved_dossier(self):
        manuscript = "# Notes de terrain\n\n## Matin\n" + "Observe la rivière.\n" * 1900 + "\nFin du manuscrit."
        stage_texts = [f"Original output {i} for {label}." for i, label in enumerate(self.stages)]
        stage_texts[5] = manuscript
        for i, text in enumerate(stage_texts):
            if i == 5:
                self.save_stage(i, {"response": json.dumps(self.packet(i, deliverable=text)), "decision": "draft"})
            self.save_stage(i, {"text": text, "notes": f"Reviewed note {i}.", "decision": "approve"})
        before = self.read()
        state = self.delivery()
        self.assertEqual(state["next"], "fabricate")
        self.assertEqual(state["approved_count"], 8)
        self.assertTrue(state["manuscript_available"])
        self.assertEqual(set(state["missing_roles"]), {"client", "preview"})
        self.assertEqual(state["status"], "Brouillon")
        for word in ("PDF", "fichier", "télécharge"):
            self.assertIn(word.casefold(), state["prompt"].casefold())
        source = self.client.get(self.base + "/delivery/manuscript")
        self.assertEqual(source.status_code, 200)
        self.assertIn("attachment", source.headers["content-disposition"])
        self.assertEqual(source.content.decode("utf-8"), manuscript)
        dossier = self.client.get(self.base + "/delivery/dossier")
        self.assertEqual(dossier.status_code, 200)
        self.assertIn("attachment", dossier.headers["content-disposition"])
        for i, original in enumerate(stage_texts):
            self.assertIn(original, dossier.text)
            self.assertIn(f"Reviewed note {i}.", dossier.text)
        self.assertIn(self.packet()["handoff"], dossier.text)
        self.assertEqual(self.read(), before)
        rejected = self.client.post(self.base + "/export", headers={"If-Match": str(before["rev"])})
        self.assertEqual(rejected.status_code, 409, "Stage approval alone cannot release a product.")
        self.save_stage(2, {"text": "Replacement design.", "decision": "approve"})
        self.assertFalse(self.delivery()["manuscript_available"])
        self.assertEqual(self.client.get(self.base + "/delivery/manuscript").status_code, 409)
        self.assertNotIn(manuscript, self.client.get(self.base + "/delivery/dossier").text)

    def test_every_specialist_gets_a_copyable_contract_for_the_current_edition(self):
        for index, label in enumerate(self.stages):
            with self.subTest(stage=label):
                mission = self.mission_data(index)
                self.assertEqual(mission["template"]["protocol"], "venture.stage.v1")
                self.assertEqual(mission["template"]["edition_id"], self.project["id"])
                self.assertEqual(mission["template"]["stage"], label)
                for field in ("protocol", "edition_id", "deliverable", "handoff"):
                    self.assertIn(field, mission["text"])
                self.assertIn(self.project["id"], mission["text"])

    def test_eight_stages_in_each_specialty_deliver_to_the_next_role_and_preserve_legacy_work(self):
        legacy = [f"Reviewed source for {name}. Keep figure {index + 17} and its stated uncertainty."
                  for index, name in enumerate(self.stages)]
        for index, source in enumerate(legacy):
            self.save_stage(index, {"text": source, "decision": "draft"})
        structures = set()
        for kind in ("livre", "imprimable", "outil"):
            changed = self.send("PUT", "/workshop-kind", {"kind": kind})
            self.assertEqual(changed.status_code, 200, changed.text)
            self.project = changed.json()
            missions = [self.mission_data(index) for index in range(len(self.stages))]
            roles = [m["text"].splitlines()[0].split(" · ")[-1] for m in missions]
            for index, stage in enumerate(self.stages):
                with self.subTest(kind=kind, stage=stage):
                    mission = missions[index]
                    lines = mission["text"].splitlines()
                    shape = next((line for line in lines if line.startswith("Structure du livrable")), "")
                    self.assertTrue(shape, "Each specialty needs a description of its stage-specific output.")
                    self.assertNotIn(shape, structures)
                    structures.add(shape)
                    recipient = next((line for line in lines if line.startswith("Destinataire")), "")
                    self.assertTrue(recipient)
                    if index + 1 < len(roles):
                        self.assertIn(roles[index + 1].casefold(), recipient.casefold())
                    self.assertIn("un seul objet JSON valide", mission["text"])
                    conversion = self.mission_data(index, "?convert=true")
                    self.assertEqual(conversion["template"], mission["template"])
                    self.assertIn(recipient, conversion["text"])
                    self.assertIn("un seul objet JSON valide", conversion["text"])
                    self.assertIn(legacy[index], conversion["text"])
                    self.assertIn("fidèlement", conversion["text"])
                    self.assertNotIn(shape, conversion["text"])
        self.assertEqual(len(structures), 24)

    def test_preview_is_read_only_and_persisted_result_waits_for_human_approval(self):
        packet = self.packet()
        fenced = "Voici le résultat.\n\n```json\n" + json.dumps(packet) + "\n```"
        before = self.read()
        response = self.preview(0, fenced)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), packet)
        self.assertEqual(self.read(), before)

        stage = self.save_stage(0, {"response": fenced, "decision": "draft", "notes": "Use page one."})
        self.assertEqual(stage["status"], "review")
        self.assertEqual(stage["packet"], packet)
        self.assertEqual(stage["text"], packet["deliverable"])
        self.assertEqual(self.project["manifest"], before["manifest"])
        self.assertNotIn(packet["handoff"], self.mission_data(1)["text"])
        for decision in ("approve", "revise"):
            with self.subTest(decision=decision):
                rejected = self.send("PUT", "/stages/0", {"response": fenced, "decision": decision, "notes": "test"})
                self.assertEqual(rejected.status_code, 422, rejected.text)
        approved = self.save_stage(0, {"text": stage["text"], "notes": stage["notes"], "decision": "approve"})
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["packet"], packet)
        self.assertIn(packet["handoff"], self.mission_data(1)["text"])

    def test_wrong_edition_stage_or_unusable_packet_does_not_replace_saved_work(self):
        self.save_stage(0, {"text": "Original author notes.", "decision": "draft"})
        p = self.packet()
        other = self.client.post(self.base + "/edition", json={"channel": "etsy", "version": "2.0"}).json()
        malformed = [
            json.dumps(self.packet(edition_id=other["id"])),
            json.dumps(self.packet(stage=self.stages[1])),
            json.dumps(self.packet(protocol="unknown")),
            json.dumps(self.packet(handoff="")),
            json.dumps(self.packet(deliverable="")),
            json.dumps(self.packet(decisions="unexpected string")),
            json.dumps(self.packet(decisions=["x"] * 13)),
            json.dumps(self.packet(suggested_metadata={"price": 12})),
            json.dumps(self.packet(status="Publié")),
            json.dumps(p).replace('"handoff":', '"handoff":"foreign value","handoff":', 1),
            json.dumps(p) + "\n" + json.dumps(p),
            "```json\n" + json.dumps(p) + "\n```\n```json\n" + json.dumps(p) + "\n```",
            "A heading, prose and an unstructured checklist.",
        ]
        before = self.read()
        for i, text in enumerate(malformed):
            with self.subTest(case=i):
                self.assertEqual(self.preview(0, text).status_code, 422)
                rejected = self.send("PUT", "/stages/0", {"response": text, "decision": "draft"})
                self.assertEqual(rejected.status_code, 422, rejected.text)
        self.assertEqual(self.read(), before)

    def test_explicit_selected_metadata_changes_feed_the_actual_product(self):
        # Use an edition with all the checked customer files so the export can ship.
        demo = self.client.post("/api/demo/etsy")
        self.assertEqual(demo.status_code, 200, demo.text)
        self.project = demo.json()
        self.base = "/api/projects/" + self.project["id"]
        packet = self.packet()
        old = self.project["manifest"]
        stage = self.save_stage(0, {"response": json.dumps(packet), "decision": "draft"})
        self.save_stage(0, {"text": stage["text"], "decision": "approve"})
        self.assertEqual(self.project["manifest"], old)
        revision = self.project["rev"]
        response = self.send("POST", "/stages/0/apply-metadata", {"fields": ["title"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.project = response.json()
        now = self.project["manifest"]
        self.assertEqual(now["title"], packet["suggested_metadata"]["title"])
        self.assertEqual(old["keywords"], now["keywords"])
        self.assertEqual(old["product_id"], now["product_id"])
        self.assertEqual(self.read(), self.project)
        stale = self.send("POST", "/stages/0/apply-metadata", {"fields": ["keywords"]}, revision=revision)
        self.assertEqual(stale.status_code, 409, stale.text)
        exported = self.client.post(self.base + "/export", headers={"If-Match": str(self.project["rev"])})
        self.assertEqual(exported.status_code, 200)
        with ZipFile(BytesIO(exported.content)) as archive:
            manifest = json.loads(archive.read("produit.json"))
            self.assertEqual(manifest["title"], packet["suggested_metadata"]["title"])
            self.assertEqual(manifest["keywords"], old["keywords"])
            self.assertIn(self.stages[0], manifest["declared_validations"])
            self.assertNotIn(packet["checks"][0], manifest["declared_checks"])
            self.assertIn(packet["suggested_metadata"]["title"], archive.read("fiche-commerciale.txt").decode())

    def test_short_handoff_and_full_source_stay_separate_after_approval(self):
        body = "Archival diagram details " * 3000 + "Unique final drawing record."
        packet = self.packet(deliverable=body)
        self.save_stage(0, {"response": json.dumps(packet), "decision": "draft"})
        self.save_stage(0, {"text": body, "decision": "approve"})
        prompt = self.mission_data(1)["text"]
        self.assertIn(packet["handoff"], prompt)
        for name in ("decisions", "open_questions", "sources", "checks"):
            self.assertIn(packet[name][0], prompt)
        self.assertNotIn("Unique final drawing record.", prompt)
        self.assertLess(len(prompt), len(body) // 3)
        full = self.client.get(self.base + "/mission/1/context")
        self.assertEqual(full.status_code, 200, full.text[:150])
        self.assertIn("Unique final drawing record.", full.text)
        self.assertEqual(self.read()["stages"][0]["text"], body)

    def test_legacy_prose_is_preserved_and_can_be_replaced_by_a_reviewed_conversion(self):
        late_recommendation = "I recommend assigning one card per trail."
        old_text = ("Legacy sample outline.\n" + "Observation notes, with dates and locations.\n" * 1300
                    + late_recommendation + "\nEnd of field notebook inventory.")
        self.save_stage(0, {"text": old_text, "decision": "approve"})
        original_revision = self.project["rev"]
        following = self.mission_data(1)["text"]
        self.assertIn("Legacy sample outline.", following)
        self.assertIn(late_recommendation, following)
        self.assertLess(len(following), len(old_text) // 3)
        conversion = self.mission_data(0, "?convert=true")["text"]
        self.assertIn("venture.stage.v1", conversion)
        self.assertEqual(self.read()["stages"][0]["text"], old_text.strip())
        replacement = self.packet(deliverable="Edited outline with the original decisions retained.")
        stage = self.save_stage(0, {"response": json.dumps(replacement), "decision": "draft"})
        self.assertEqual(stage["status"], "review")
        history = self.client.get(f"{self.base}/history/{original_revision}").json()
        self.assertEqual(history["stages"][0]["text"], old_text.strip())

    def test_editing_deliverable_removes_obsolete_structured_handoff(self):
        original = self.packet()
        self.save_stage(0, {"response": json.dumps(original), "decision": "draft"})
        self.save_stage(0, {"text": original["deliverable"], "decision": "approve"})
        self.save_stage(1, {"text": "Evidence summary.", "decision": "approve"})
        self.save_stage(0, {"text": "The layout now uses recycled card.", "decision": "approve"})
        current = self.read()
        self.assertFalse(current["stages"][0].get("packet"))
        self.assertEqual(current["stages"][1]["status"], "review")
        next_prompt = self.mission_data(1)["text"]
        self.assertNotIn(original["handoff"], next_prompt)
        self.assertIn("recycled card", next_prompt)

    def test_change_workshop_track_keeps_edition_and_approved_work(self):
        self.save_stage(0, {"text": "Approved project direction.", "decision": "approve"})
        old = self.project
        changed = self.send("PUT", "/workshop-kind", {"kind": "outil"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.project = changed.json()
        self.assertEqual(self.project["workshop_kind"], "outil")
        self.assertEqual(self.project["manifest"], old["manifest"])
        self.assertEqual(self.project["stages"], old["stages"])
        self.assertIn("formules", self.mission_data(2)["text"].lower())
        restored = self.send("PUT", "/workshop-kind", {"kind": None})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.project = restored.json()
        self.assertIsNone(self.project.get("workshop_kind"))
        self.assertIn("imprim", self.mission_data(2)["text"].lower())
