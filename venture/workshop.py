import json
import re

from .stage_reply import reply_template


STAGES = [
 ("Direction","Directeur de collection","Responsable produit","Définis le lecteur, son besoin, la promesse et les exclusions. Propose trois critères mesurables et tranche les choix à faire.","Décris l'utilisateur, sa décision, ses données disponibles et trois critères de réussite mesurables."),
 ("Recherche","Documentaliste","Analyste métier","Documente les questions du lecteur. Pour chaque affirmation vérifiable donne la source, la date et le passage pertinent. Signale les lacunes.","Relie chaque règle de calcul à une source ou à une hypothèse explicite. Donne les unités, exceptions et données inconnues."),
 ("Conception","Architecte éditorial","Concepteur fonctionnel","Organise le contenu en unités adaptées à la forme retenue dans le brief (chapitres, doubles pages ou activités). Donne pour chaque unité son objectif, sa place et un exemple. Choisis une unité pilote.","Décris les entrées, validations, formules, sorties et un exemple calculé à la main. Dessine la structure des feuilles."),
 ("Pilote","Auteur du chapitre pilote","Concepteur du prototype","Écris le chapitre pilote. Utilise les sources retenues, des exemples concrets et la voix convenue.","Réalise un prototype sur un cas réel anonymisé. Livre le fichier modifiable, le mode d'emploi et le résultat attendu."),
 ("Revue du pilote","Lecteur critique","Testeur indépendant","Évalue le pilote avec les critères de direction. Cite les passages à revoir, la correction et sa priorité.","Recalcule les résultats indépendamment. Essaie zéro, données absentes, arrondis et erreurs d'unité. Indique prévu, obtenu et écart."),
 ("Production","Responsable de rédaction","Développeur de l'outil","Rédige les sections convenues en conservant la terminologie et le ton du pilote approuvé. Livre le manuscrit et les références.","Réalise les fonctions validées, la gestion des erreurs et les exemples. Fournis le fichier source et la version client."),
 ("Contrôle qualité","Secrétaire de rédaction","Responsable recette","Vérifie cohérence, anglais, sources, renvois et droits documentés. Relève chaque anomalie avec un emplacement et une correction.","Exécute les cas de recette. Vérifie formules, saisie, compatibilité et lisibilité. Distingue les tests exécutés des propositions."),
 ("Finition","Responsable de fabrication","Responsable livraison","Vérifie la hiérarchie visuelle, les légendes, les pages liminaires et les fichiers de couverture. Rends la liste des fichiers livrables.","Finalise la notice, les exemples, les noms de fichiers et les visuels montrant le produit livré.")
]
PRINTABLE = [
 "Définis l'usage sur papier, l'acheteur, l'action à accomplir et la taille de la zone d'écriture.",
 "Recense les informations réellement nécessaires et les conventions du public cible.",
 "Décris le gabarit, les rubriques, la grille, l’ordre de lecture et les zones de réponse. Pour un cahier d’activités, établis le plan activité par activité avec objectif, consigne, déroulement, exemple ou solution, progression et activité pilote. Précise les formats de page et variantes prévus dans le brief.",
 "Livre une page pilote éditable et un PDF à imprimer à 100 %.",
 "Fais examiner un exemplaire rempli. Documente les ambiguïtés et les manques de place.",
 "Réalise la série approuvée avec des styles cohérents et les formats papier convenus.",
 "Contrôle une impression réelle, contrastes, débordements et facilité de remplissage.",
 "Prépare les PDF clients et des aperçus fidèles aux pages livrées."
]

PRINTABLE_ROLES = [
    "Directeur de collection d’imprimables", "Documentaliste",
    "Concepteur d’activités et de supports imprimables", "Maquettiste du prototype",
    "Responsable des essais d’usage", "Responsable de production des imprimables",
    "Contrôleur qualité des imprimables", "Responsable de fabrication",
]

# The reply envelope is shared. The document inside it is specific to the profession.
DELIVERABLES = {
    "livre": (
        "Une note de décision avec public, promesse motivée, exclusions et critères d’acceptation mesurables.",
        "Une matrice question du lecteur / preuve et référence / limite / conséquence pour le livre.",
        "Un sommaire ordonné, avec objectif, matière, exemple et lien vers l’unité suivante. Désigne et justifie le pilote.",
        "Le texte du pilote prêt à relire, avec son titre, ses exemples, ses références et les passages à confirmer.",
        "Un relevé par passage : critère, citation, constat, gravité et correction proposée. Termine par un avis motivé.",
        "Le manuscrit des sections demandées dans l’ordre approuvé, avec références et repérage des éléments manquants.",
        "Un registre des anomalies : emplacement, preuve, impact, correction et vérification effectuée ou restant à faire.",
        "Un inventaire de livraison : fichier, version, usage, vérification observée et pièce restant à obtenir.",
    ),
    "imprimable": (
        "Une note de cadrage : utilisateur, activité sur papier, promesse, exclusions, critères mesurables et formats retenus ou proposés.",
        "Une matrice besoin / observation ou référence / limite / conséquence sur la consigne ou le gabarit.",
        "Une fiche par activité : objectif, consigne prête à imprimer, étapes, exemple ou corrigé, zone de réponse et variante de format. Identifie les fiches pilotes.",
        "Le contenu complet d’une fiche pilote et son corrigé si pertinent. Identifie séparément la source éditable, le PDF produit et les fichiers restant à fabriquer.",
        "Une grille d’essai : fiche et zone, action, observation réelle, difficulté, correction et essai encore nécessaire.",
        "Les fiches complètes dans l’ordre prévu, leurs corrigés et variantes. Indique pour chaque série le contenu prêt et les fichiers produits.",
        "Un rapport par page et format : dimensions, lisibilité, zone de réponse, défaut observé et action. Consigne les impressions restant à tester.",
        "Un inventaire des PDF et aperçus : fichier, format, nombre de pages vérifiable, statut de livraison et contrôle effectué.",
    ),
    "outil": (
        "Une décision produit motivée : utilisateur, décision à prendre, entrées disponibles, périmètre et critères mesurables.",
        "Une matrice règle / source ou hypothèse / unité / exception / conséquence pour les calculs.",
        "Une spécification des entrées et sorties, un tableau des validations et formules, puis un exemple chiffré avec résultat attendu.",
        "Une notice de prototype : données d’exemple, parcours, résultats attendus et fichiers effectivement disponibles.",
        "Un tableau des cas : entrée, attendu, obtenu si observé, écart et priorité. Signale les cas restant à exécuter.",
        "Les fonctions livrées avec entrées, sorties, erreurs gérées et exemples. Identifie les sources et fichiers client effectivement produits.",
        "Un registre de recette : environnement, cas, résultat attendu, résultat observé, anomalie et état du contrôle.",
        "Un inventaire de livraison : version, fichier source et client, notice, exemple et contrôle effectué.",
    ),
}


def _excerpt(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit - 2].rstrip() + " …"


def _legacy_excerpt(text, limit=1150):
    """Verbatim legacy evidence only. Give late recommendations and constraints a place."""
    if len(text) <= limit:
        return text
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    if not lines:
        return ""
    groups = [
        # Sentence-level extraction keeps a late recommendation in a long final paragraph.
        (r"\b(?:I recommend|we recommend|je recommande|nous recommandons|recommandation|recommendation[s]?)\b", "sentence"),
        (r"^\d+[.)]\s+|\*\*(?:audience|public cible|scope|périmètre|positioning|positionnement)\b", "line"),
        (r"^\|[^|]*(?:page sizes?|paper sizes?|formats? (?:de page|papier)|dimensions?|couleurs?|colou?rs?|visual treatment|traitement visuel|variantes?)\b[^|]*\|", "line"),
        (r"^\|[^|]*(?:formats?|structure|scope|portée|unités?|units?|variables?|livrables?|deliverables?)\b[^|]*\|", "line"),
        (r"^\*\*(?:not completed|open question|à vérifier|reste à|questions ouvertes|limits?|non réalisé|non vérifié)\b", "line"),
    ]
    chosen = []
    for pattern, unit in groups:
        matches = []
        for line in lines:
            candidates = re.split(r"(?<=[.!?])\s+", line) if unit=="sentence" else [line]
            matches.extend(c for c in candidates if re.search(pattern,c,re.IGNORECASE))
        if matches:
            if unit=="sentence":
                chosen.append(matches[-1])
            else:
                chosen.extend(matches[:2])
    # The original opening and closing paragraphs support prose with no heading conventions.
    informational = [s for s in lines if not s.startswith("#") and not re.fullmatch(r"[|:\s-]+",s)]
    chosen.extend(informational[:1])
    chosen.extend(informational[-1:])
    candidates = []
    for line in chosen:
        # A fallback paragraph may contain the very recommendation already selected.
        if not any(line in previous or previous in line for previous in candidates):
            candidates.append(line)
        if len(candidates) == 9:
            break
    if not candidates:
        return _excerpt(text,limit)
    # Allocate unused space from short rows to long decisions, in priority order.
    remaining = limit - 5 * (len(candidates) - 1)
    budgets = [0] * len(candidates)
    for count, i in enumerate(sorted(range(len(candidates)), key=lambda i: len(candidates[i]))):
        budgets[i] = min(len(candidates[i]), remaining // (len(candidates) - count))
        remaining -= budgets[i]
    focus = re.search(r"\b(?:I recommend|we recommend|je recommande|nous recommandons)\b", candidates[0], re.IGNORECASE)
    if focus and len(candidates[0]) > budgets[0]:
        candidates[0] = candidates[0][focus.start():]
    return " […] ".join(_excerpt(line, space) for line, space in zip(candidates, budgets))


def _stage_context(stage, budget, *, latest=False):
    packet = stage.get("packet")
    if not packet:
        return "Extraits du texte enregistré :\n" + _legacy_excerpt(stage["text"], budget - 35)
    # Keep distinct provenance and pending work even when the main brief is long.
    handoff = packet["handoff"] if latest else _excerpt(packet["handoff"], min(700, budget // 2))
    lines = ["Passation : " + handoff]
    for label, key in [
        ("Orientations consignées", "decisions"), ("Questions ouvertes", "open_questions"),
        ("Sources déclarées", "sources"), ("Contrôles déclarés", "checks"),
    ]:
        entries = packet.get(key, [])
        if entries:
            length = max(45, (budget // 2 - 170) // 8)
            shown = [_excerpt(item, length) for item in entries[:2]]
            lines.append(label + " : " + " | ".join(shown) + (" […]" if len(entries)>2 else ""))
    return "\n".join(lines)


def complete_context(project, index):
    """Markdown attachment with exact text. Default prompts remain compact."""
    m = project["manifest"]
    parts = [f"# {m['title']} — {STAGES[index][0]}", f"Version {m['version']} · {m['channel']}",
             "## Brief de l’édition", m.get("brief") or m.get("description") or "Non renseigné."]
    for pos, stage in enumerate(project["stages"][:index+1]):
        if pos < index and stage["status"] != "approved":
            continue
        if not stage["text"] and not stage["notes"]:
            continue
        label = "Étape en cours" if pos == index else "Étape validée dans l’application"
        parts.extend([f"## {label} · {STAGES[pos][0]}", stage["text"]])
        if stage.get("packet"):
            extra = {k:v for k,v in stage["packet"].items() if k not in ("deliverable",)}
            parts.extend(["### Informations de passation", json.dumps(extra, ensure_ascii=False, indent=2)])
        if stage["notes"]:
            parts.extend(["### Observations enregistrées", stage["notes"]])
    return "\n\n".join(parts) + "\n"


def mission(project, index, *, convert=False, include_current=True):
    m = project["manifest"]
    row = STAGES[index]
    kind = project.get("workshop_kind") or m["kind"]
    if kind == "outil":
        role, task = row[2], row[4]
    elif kind == "imprimable":
        role, task = PRINTABLE_ROLES[index], PRINTABLE[index]
    else:
        role, task = row[1], row[3]

    recipient = "responsable de la livraison"
    if index + 1 < len(STAGES):
        recipient = PRINTABLE_ROLES[index + 1] if kind == "imprimable" else STAGES[index + 1][2 if kind == "outil" else 1]
    current = project["stages"][index]
    template = reply_template(project["id"], row[0])
    parts = [
        f"Venture Publisher · {row[0]} · {role}",
        f"Produit : {m['title']} · Édition {m['version']} · Destination {m['channel']} · Spécialité {kind}. "
        f"Écris le livrable dans la langue {m['language']}.",
        f"Destinataire : {recipient}. Tu prépares son dossier de travail. L’Atelier importera ta réponse pour lui transmettre la passation.",
    ]
    if convert:
        parts.append(
            "Conversion d’une ancienne réponse. Reprends fidèlement son livrable dans deliverable, y compris ses sources, "
            "hypothèses et limites. Organise la passation à partir de ce texte. Ne réalise pas la mission une seconde fois.")
        if include_current and current["text"] and len(current["text"]) <= 15000:
            parts.extend(["Texte source à convertir :", current["text"]])
        elif include_current and current["text"]:
            parts.append("La réponse est longue. Utilise le texte intégral de l’étape en cours dans le dossier de contexte joint. "
                         "Demande cette pièce si elle manque.")
        else:
            parts.append("Utilise l’ancienne réponse que l’utilisateur colle ou joint avec cette consigne. Demande-la si elle manque.")
    else:
        parts.extend([
            "Brief de l’édition : " + _excerpt(m["brief"] or m["description"] or "À préciser par la direction.", 900),
            "Mission : " + task,
            "Structure du livrable : " + DELIVERABLES[kind][index],
        ])
        prior = [(pos, stage) for pos,stage in enumerate(project["stages"][:index]) if stage["status"] == "approved"]
        if prior:
            parts.append("Contexte des étapes validées dans l’Atelier. Les extraits servent au cadrage. Les mesures prévues "
                         "et les contrôles déclarés par un spécialiste gardent leur statut d’origine.")
        for pos,stage in prior:
            parts.append(STAGES[pos][0] + "\n" + _stage_context(stage, min(1350, 5500 // len(prior)), latest=pos == prior[-1][0]))
        if current["text"]:
            parts.append("Livrable actuel à reprendre (extrait si nécessaire) :\n" + _legacy_excerpt(current["text"], 700))
        if current["notes"]:
            parts.append("Observations de l’utilisateur :\n" + _excerpt(current["notes"], 650))
        active = [f for f in project["files"] if f["active"]]
        if active:
            names = ", ".join(f"{f['name']} ({f['role']})" for f in active)
            parts.append("Fichiers enregistrés dans l’application : " + _excerpt(names, 520) +
                         ". Leur lecture exige que l’utilisateur les joigne à la discussion.")
        parts.append("Le dossier de contexte téléchargeable dans l’Atelier contient les textes complets. "
                     "Demande les pièces nécessaires si une donnée indispensable manque.")

    parts.extend([
        "Format de retour pour l’application : réponds avec un seul objet JSON valide, directement copiable, sans clôture Markdown, "
        "salutation, préambule, offre finale ni texte autour. Garde les noms de champs anglais inchangés et recopie les valeurs "
        "de protocol, edition_id et stage exactement. Remplis deliverable avec le travail de cette étape "
        "(Markdown dans une chaîne JSON, avec \\n pour les sauts de ligne). N’annonce un fichier ou un PDF produit que s’il existe. "
        "Pour une pièce à fabriquer, donne le contenu ou le plan et indique ce qui reste à produire. "
        "Évite de recopier les étapes antérieures. Remplis handoff avec une synthèse autonome pour le prochain spécialiste "
        "(maximum 1 100 caractères, chiffres et contraintes utiles). Ces deux champs sont obligatoires.",
        "Dans decisions, consigne les orientations et précise lesquelles restent proposées. Dans open_questions, garde "
        "les arbitrages et les données manquantes. Dans sources, indique les références réellement consultées. Dans checks, "
        "indique les contrôles et leurs résultats observés. Place les essais projetés dans open_questions en les marquant « à réaliser ». "
        "Ces quatre listes acceptent 12 chaînes de 600 caractères au maximum "
        "chacune. Utilise [] si vide. suggested_metadata peut proposer title, subtitle, description, category ou keywords "
        "(liste de mots-clés) seulement lorsque justifié ; sinon garde {}. L’utilisateur validera les propositions dans l’Atelier.",
        json.dumps(template, ensure_ascii=False, indent=2),
    ])
    return "\n\n".join(parts)
