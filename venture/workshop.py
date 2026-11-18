STAGES = [
 ("Direction","Directeur de collection","Responsable produit","Définis le lecteur, son besoin, la promesse et les exclusions. Propose trois critères mesurables et tranche les choix à faire.","Décris l'utilisateur, sa décision, ses données disponibles et trois critères de réussite mesurables."),
 ("Recherche","Documentaliste","Analyste métier","Documente les questions du lecteur. Pour chaque affirmation vérifiable donne la source, la date et le passage pertinent. Signale les lacunes.","Relie chaque règle de calcul à une source ou à une hypothèse explicite. Donne les unités, exceptions et données inconnues."),
 ("Conception","Architecte éditorial","Concepteur fonctionnel","Propose un sommaire annoté, un objectif par chapitre, un exemple et le chapitre pilote.","Décris les entrées, validations, formules, sorties et un exemple calculé à la main. Dessine la structure des feuilles."),
 ("Pilote","Auteur du chapitre pilote","Concepteur du prototype","Écris le chapitre pilote. Utilise les sources retenues, des exemples concrets et la voix convenue.","Réalise un prototype sur un cas réel anonymisé. Livre le fichier modifiable, le mode d'emploi et le résultat attendu."),
 ("Revue du pilote","Lecteur critique","Testeur indépendant","Évalue le pilote avec les critères de direction. Cite les passages à revoir, la correction et sa priorité.","Recalcule les résultats indépendamment. Essaie zéro, données absentes, arrondis et erreurs d'unité. Indique prévu, obtenu et écart."),
 ("Production","Responsable de rédaction","Développeur de l'outil","Rédige les sections convenues en conservant la terminologie et le ton du pilote approuvé. Livre le manuscrit et les références.","Réalise les fonctions validées, la gestion des erreurs et les exemples. Fournis le fichier source et la version client."),
 ("Contrôle qualité","Secrétaire de rédaction","Responsable recette","Vérifie cohérence, anglais, sources, renvois et droits documentés. Relève chaque anomalie avec un emplacement et une correction.","Exécute les cas de recette. Vérifie formules, saisie, compatibilité et lisibilité. Distingue les tests exécutés des propositions."),
 ("Finition","Responsable de fabrication","Responsable livraison","Vérifie la hiérarchie visuelle, les légendes, les pages liminaires et les fichiers de couverture. Rends la liste des fichiers livrables.","Finalise la notice, les exemples, les noms de fichiers et les visuels montrant le produit livré.")
]
PRINTABLE = [
 "Définis l'usage sur papier, l'acheteur, l'action à accomplir et la taille de la zone d'écriture.",
 "Recense les informations réellement nécessaires et les conventions du public cible.",
 "Propose un gabarit avec rubriques, grille, ordre de lecture et espace d'écriture.",
 "Livre une page pilote éditable et un PDF à imprimer à 100 %.",
 "Fais examiner un exemplaire rempli. Documente les ambiguïtés et les manques de place.",
 "Réalise la série approuvée avec des styles cohérents et les formats papier convenus.",
 "Contrôle une impression réelle, contrastes, débordements et facilité de remplissage.",
 "Prépare les PDF clients et des aperçus fidèles aux pages livrées."
]
def mission(project, index):
    m=project["manifest"]
    row=STAGES[index]
    tool=m["kind"]=="outil"
    role=row[2] if tool else row[1]
    task=row[4] if tool else row[3]
    if m["kind"]=="imprimable":
        task=PRINTABLE[index]
    earlier=[f"{STAGES[i][0]}\n{s['text']}" for i,s in enumerate(project["stages"][:index]) if s["status"]=="approved"]
    current=project["stages"][index]
    files="\n".join(f"- {f['name']} ({f['role']})" for f in project["files"] if f["active"])
    return "\n\n".join(filter(None,[
        f"Tu interviens comme {role} pour « {m['title']} », version {m['version']}.",
        f"Destination : {m['channel']}. Langue des livrables : {m['language']}. Brief : {m['brief'] or m['description'] or 'À préciser par la direction.'}",
        "Décisions et livrables approuvés en amont :\n"+"\n\n".join(earlier) if earlier else "",
        "Mission : "+task,
        "Fichiers locaux à joindre si nécessaires (les fichiers ne sont pas transférés par cette consigne) :\n"+files if files else "",
        "Version à revoir :\n"+current["text"] if current["text"] else "",
        "Corrections demandées :\n"+current["notes"] if current["notes"] else "",
        "Rends le livrable utilisable, les sources ou hypothèses, les contrôles effectivement réalisés et les décisions qui nécessitent mon accord. Indique tout document auquel tu n'as pas eu accès."
    ]))
