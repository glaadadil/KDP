"""Read-only handoff from editorial approval to actual production files."""
from . import quality, store
from .models import CHANNELS, ROLES
from .workshop import STAGES, complete_context


PRODUCTION = next(i for i, stage in enumerate(STAGES) if stage[0] == "Production")
REQUIRED = {
    "etsy": {"client": None, "preview": {".jpg", ".jpeg", ".png"}},
    "paper": {"interior": {".pdf"}, "cover": {".pdf"}},
    "kindle": {"ebook": {".epub"}, "cover": {".jpg", ".jpeg"}},
}
SPECIALTY = {
    "livre": "Compose le texte, les titres et les illustrations prévus dans le manuscrit validé. "
             "Si le dossier décrit des fiches ou un cahier d’activités, réalise chaque activité, ses zones de réponse et ses corrigés convenus.",
    "imprimable": "Compose chaque fiche imprimable avec sa consigne, ses zones de réponse et les corrigés prévus dans le dossier. "
                  "Préserve l’espace d’écriture, la progression et le traitement visuel approuvés.",
    "outil": "Réalise l’outil modifiable convenu. Pour un tableur, livre un XLSX ou un ODS fonctionnel avec les formules, "
            "les validations de saisie et l’exemple approuvés. Joins la notice d’utilisation prévue.",
}


def fabrication_prompt(project, kind):
    m = project["manifest"]
    channel = m["channel"]
    parts = [
        f"Mission de fabrication — {m['title']} · édition {m['version']} · {CHANNELS[channel]}.",
        f"Langue du produit : {m['language']}. Utilise le dossier de fabrication Markdown joint et le texte de Production pour fabriquer le produit final. "
        "Production contient le contenu à composer. Applique les corrections de Contrôle qualité et les choix de Finition. "
        "Le brief et les décisions validées font foi pour le contenu, le format et les variantes. Demande le dossier s’il manque.",
        "Fournis maintenant les vrais fichiers téléchargeables dans cette conversation, chacun avec un lien ou une pièce jointe qui s’ouvre. "
        "Le résultat attendu est le produit utilisable, accompagné de sa source modifiable. "
        "Ne réponds ni en JSON ni par un inventaire, une spécification ou une nouvelle mission.",
        SPECIALTY[kind],
    ]
    if channel == "etsy":
        buyer = ("Génère le fichier client de l’outil dans le format convenu." if kind == "outil" else
                 "Génère le PDF client complet prêt à télécharger ou les fichiers client convenus dans le dossier.")
        parts.append(
            f"Etsy numérique. {buyer} Pour un produit à imprimer, fournis les PDF prêts à imprimer à 100 % "
            "aux formats validés. Si A4 et US Letter sont convenus, exporte deux PDF distincts depuis la source. "
            "Crée séparément un aperçu commercial PNG ou JPEG fidèle aux pages ou écrans réellement réalisés. "
            "Distingue la source de travail, le produit client et l’aperçu.")
    elif channel == "paper":
        opt = m["print"]
        parts.append(
            f"KDP broché. Génère un PDF intérieur et une couverture complète en PDF séparé (première, dos, quatrième). "
            f"Réglages de cette édition : format de coupe {opt['trim']} pouces, papier {opt['paper']}, "
            f"fond perdu {'oui' if opt['bleed'] else 'non'}. Détermine la tranche à partir de la pagination réelle et du gabarit correspondant. "
            "Si le gabarit nécessaire manque, demande-le et indique quelle pièce reste à générer.")
    else:
        parts.append(
            "Kindle. Génère le manuscrit EPUB avec navigation et la couverture JPEG séparée. "
            "Adapte la mise en page à la lecture numérique. Si une activité ou un calcul nécessite une adaptation, "
            "applique celle convenue dans le dossier ou signale l’arbitrage nécessaire.")
    parts.extend([
        "Respecte les variantes destinées à l’acheteur. Si le dossier demande des épreuves de contrôle, génère-les séparément "
        "dans les formats convenus et identifie-les pour la relecture. Vérifie le nombre de fichiers client contre la liste validée.",
        "Utilise le contenu validé et les éléments disponibles dont l’usage est autorisé. "
        "Demande les sources, images ou réglages indispensables manquants. N’invente ni contenu approuvé, ni spécifications, ni visuels, ni résultats d’essai. "
        "Ouvre et vérifie les fichiers réellement générés si tes outils le permettent. Signale toute épreuve papier ou vérification humaine encore à faire.",
        "Si tu ne peux pas créer ou joindre de fichiers ici, indique cette limite et fournis la source complète directement enregistrable "
        "dans un format adapté, avec les étapes précises pour la convertir et l’exporter. Ne simule aucun lien de téléchargement.",
    ])
    return "\n\n".join(parts)


def approved_dossier(project):
    m = project["manifest"]
    text = complete_context(project, len(STAGES) - 1, approved_only=True)
    details = [
        "## Paramètres de fabrication",
        f"Spécialité de l’Atelier : {project.get('workshop_kind') or m['kind']}",
        f"Destination : {CHANNELS[m['channel']]}",
        f"Langue : {m['language']}",
    ]
    if m["expected"]:
        details.append("### Fichiers attendus dans la fiche produit")
        details.extend(f"- {item['name']} ({ROLES[item['role']]})" for item in m["expected"])
    active = [file for file in project["files"] if file["active"]]
    if active:
        details.append("### Fichiers enregistrés dans l’application (à joindre séparément si nécessaires)")
        details.extend(f"- {file['name']} ({ROLES[file['role']]})" for file in active)
    return text + "\n" + "\n".join(details) + "\n"


def overview(project):
    m = project["manifest"]
    channel = m["channel"]
    kind = project.get("workshop_kind") or m["kind"]
    stages = project["stages"]
    count = sum(s["status"] == "approved" for s in stages)
    approved = count == len(STAGES)
    active = [f for f in project["files"] if f["active"]]
    usable = [f for f in active if not f["info"].get("error") and store.original(f).is_file()]
    ready = [
        role for role, extensions in REQUIRED[channel].items()
        if any(f["role"] == role and (extensions is None or f["info"]["ext"] in extensions) for f in usable)
    ]
    missing = [role for role in REQUIRED[channel] if role not in ready]
    blocking = sum(item["level"] == "error" for item in quality.rows(project))
    status = project["status"]
    if status == "Publié":
        action = "published"
    elif status in ("Dépôt en cours", "Soumis", "En examen"):
        action = "deposit"
    elif missing and approved:
        action = "fabricate"
    elif missing and not active:
        action = "workshop"
    elif missing or blocking or status == "Correction nécessaire":
        action = "check"
    else:
        action = "deposit"
    return {
        "approved": approved, "approved_count": count,
        "next": action, "status": status, "kind": kind, "channel": channel,
        "missing_roles": missing, "ready_roles": ready, "blocking_count": blocking,
        "manuscript_available": stages[PRODUCTION]["status"] == "approved",
        "prompt": fabrication_prompt(project, kind) if approved else "",
    }
