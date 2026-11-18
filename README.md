# Venture Publisher

Application de bureau locale pour piloter un produit éditorial, préparer ses fichiers et suivre son dépôt sur Etsy ou Amazon KDP. L’interface est en français. Les consignes de production respectent la langue choisie pour le produit.

## Démarrer sur Windows

**Version autonome x64** — Depuis les [versions du dépôt](https://github.com/glaadadil/KDP/releases), télécharge l’archive Windows publiée. Extrais **tout le ZIP**, puis ouvre `VenturePublisher.exe`. Le dossier `_internal` doit rester à côté de l’exécutable. Cette distribution contient Python et les dépendances. Pour restaurer une sauvegarde avec la version autonome, utilise `VenturePublisher.exe --restore sauvegarde.zip nouveau-dossier`.

Pour mettre à jour une installation, ferme l’ancien lanceur, extrais la nouvelle archive dans un autre dossier et démarre le nouvel exécutable. Il retrouve les éditions enregistrées dans le même dossier de données (par défaut `VenturePublisher` sous ton dossier personnel).

### Démarrer à partir du code source

1. Installe **Python 3.11 ou 3.12** depuis [python.org](https://www.python.org/downloads/windows/) avec le lanceur Python activé.
2. Télécharge le dépôt avec **Code → Download ZIP**, puis extrais-le dans un dossier où tu peux écrire.
3. Double-clique sur **Demarrer-Windows.cmd**. Le premier démarrage installe les dépendances dans un environnement isolé et nécessite Internet. Les démarrages suivants réutilisent cet environnement.
4. Garde la fenêtre du lanceur ouverte. L’interface s’ouvre dans ton navigateur à **http://127.0.0.1:8765**. Ferme le serveur avec Ctrl+C.

Sous Linux ou WSL2, lance `python3 lancer.py`. Avec WSL, si le navigateur Windows ne s’ouvre pas automatiquement, ouvre l’adresse locale affichée. Pour changer de port, utilise par exemple `python lancer.py --port 8768`.

## Utiliser l’application

- **Première visite.** Clique sur **Ouvrir un exemple complet**, puis choisis la destination. Chaque exemple utilise des fichiers fictifs. Contrôle-les puis télécharge le ZIP et ouvre-le pour voir les éléments à déposer. Le PDF broché de démonstration comporte 24 pages. Les fichiers sont destinés aux essais locaux.
- **Nouveau produit.** Crée un projet et choisis la famille (livre, outil de calcul, imprimable), la destination, la langue et la version. Si les fichiers sont déjà prêts, ouvre directement **Importer**.
- **Atelier.** Huit missions couvrent la direction, la recherche, la conception, le pilote, sa revue, la production, la qualité et la finition. Chaque spécialiste reçoit les conclusions approuvées des étapes précédentes. Conserve les fichiers modifiables dans **Importer** avec le rôle « Source de travail ».
- **Fiche.** Saisis ou ajuste les métadonnées, la devise, le prix et le rôle de l’IA. Les zones de saisie de la fiche et de l’atelier conservent le brouillon dans ce navigateur. Le bouton d’enregistrement le transfère dans la base locale et son historique. En cas de conflit entre deux onglets, la modification périmée est refusée.
- **Import.** Utilise le sélecteur ou le glisser-déposer. Le rôle est lu dans le manifeste, sinon tu le confirmes dans la liste. Un fichier différent importé sous un nom identique crée une nouvelle version. Les anciens originaux restent téléchargeables. Les fichiers de travail sont exclus du dossier commercial.
- **Import groupé.** Depuis la bibliothèque, ouvre **Importer une fiche**. Fournis le JSON seul, colle-le ou dépose un ZIP contenant `produit.json` et les fichiers. Pour une archive vendue telle quelle au client, dépose-la à l’intérieur du projet avec le rôle « Fichier client ».
- **Contrôles.** Les erreurs bloquent l’export. Les avertissements et vérifications humaines restent visibles dans le ZIP. Pour le papier sont pris en charge les formats 5 × 8, 5,5 × 8,5, 6 × 9, 7 × 10 et 8 × 10 pouces, quatre combinaisons encre/papier, avec ou sans fond perdu. L’application contrôle dimensions, pagination, couverture complète, polices et cohérence du dos. Elle demande une inspection humaine du rognage, du contenu près des bords et du rendu final. Kindle dispose d’un parcours EPUB + couverture JPEG, avec contrôle de structure et recommandation de prévisualisation.
- **Publication assistée.** Télécharge le dossier ZIP, ouvre la plateforme depuis l’onglet **Dépôt**, examine les frais, les droits et les déclarations, puis renseigne le statut effectivement constaté. Le passage à « Publié » demande une référence. Chaque édition possède sa propre fiche, son historique et son suivi. Utilise **Nouvelle édition** pour adapter une version ou changer de canal.
- **Etsy.** Le mode manuel fonctionne sans connexion. Les formats de tableur et autres sources non directement acceptées dans ce parcours sont enveloppés dans un ZIP par fichier client. Les aperçus sont séparés des fichiers achetés. Le contrôle local fixe 20 000 000 octets comme plafond prudent par téléchargement. Une notice consomme l’un des cinq emplacements.
- **Sauvegarde.** Clique sur **Sauvegarder** pour obtenir un ZIP cohérent de la base et des originaux référencés, y compris les anciennes versions. Les formulaires encore présents uniquement dans le navigateur doivent d’abord être enregistrés.

### Faire travailler les spécialistes avec ChatGPT

1. Ouvre une étape dans **Atelier**, clique sur **Copier la mission** et colle-la dans ChatGPT. La consigne contient le format de réponse attendu pour cette édition et cette étape. **Télécharger le contexte complet** permet aussi de joindre les livrables précédents à la discussion.
2. Copie toute la réponse de ChatGPT. Dans l’étape, clique sur **Importer la réponse ChatGPT**. Colle la réponse ou choisis son fichier `.json`, puis clique sur **Vérifier la réponse**.
3. Relis le livrable et la transmission destinée au spécialiste suivant. Clique sur **Enregistrer pour validation**. L’étape passe à **À valider**. Tu peux ensuite noter une correction ou choisir **Valider l’étape** pour poursuivre. Une modification à un résultat déjà approuvé remet les étapes suivantes en relecture. Les résultats précédents restent accessibles dans **Historique**.
4. Si le spécialiste propose un titre, une description ou d’autres changements de fiche, compare-les aux valeurs actuelles. Coche les champs à reprendre et clique sur **Appliquer les champs cochés**.

Pour reprendre une ancienne réponse en prose, colle-la dans **Importer la réponse ChatGPT** et choisis **Adapter une réponse en texte libre**. Colle la consigne obtenue dans ChatGPT, puis importe la réponse convertie. Si le texte est déjà enregistré dans l’étape, tu peux laisser la zone de collage vide avant de demander la conversion. Le champ **Résultat du spécialiste** reste disponible pour la rédaction manuelle.

Pour un cahier d’activités classé initialement comme livre, ouvre **Spécialité des missions**, sélectionne **Imprimable** et clique sur **Appliquer le parcours**. Les missions suivantes demanderont des éléments adaptés aux fiches et activités. Les éditions existantes conservent leurs fichiers et leur historique.

### Restaurer ou déplacer la bibliothèque

Par défaut, le catalogue et les originaux se trouvent dans **VenturePublisher** sous ton dossier personnel. Les projets ne sont jamais écrits dans le dépôt par l’application. Le ZIP de sauvegarde contient tes manuscrits et ton historique et doit être conservé dans un emplacement privé.

Ferme le serveur et restaure vers un **nouveau dossier**. Voici un exemple Windows, à lancer dans une invite de commandes depuis le dossier de l’application.

```bat
py -3 restaurer.py "D:\Sauvegardes\Venture-sauvegarde.zip" "D:\Venture-restaure"
set "VP_DATA=D:\Venture-restaure"
Demarrer-Windows.cmd
```

Le programme vérifie SQLite et les empreintes des originaux avant de rendre le répertoire restauré disponible. Pour conserver ce choix aux lancements suivants, définis la variable utilisateur Windows `VP_DATA` avec cette valeur.

## Connecter une boutique Etsy

Le parcours en ligne requiert une application autorisée par Etsy, une boutique compatible et ses paramètres développeur. Les paquets Etsy manuels restent utilisables indépendamment.

1. Dans les paramètres de ton application Etsy, enregistre exactement l’URI de retour HTTPS locale, par exemple `https://localhost:8766/etsy-return`. Utilise uniquement une URI acceptée par Etsy pour ton application.
2. Depuis la bibliothèque clique sur **Connexion Etsy**. Renseigne clé, secret, ID numérique de boutique et URI de retour. Ces paramètres restent en mémoire jusqu’à la déconnexion ou l’arrêt. Pour une configuration gérée par le système, l’alternative est de fournir au processus les variables `VP_ETSY_KEY`, `VP_ETSY_SECRET`, `VP_ETSY_SHOP` et `VP_ETSY_REDIRECT`.
3. Lance l’autorisation puis ouvre le lien officiel. Connecte-toi chez Etsy. Après l’accord, copie l’adresse complète de retour vers le champ de l’application. Cette adresse contient un code éphémère. Il est normal que le navigateur ne trouve pas de page sur le port de retour, car la reprise est manuelle. L’application vérifie la destination, le délai et le paramètre OAuth state avant l’échange PKCE. Les jetons restent en mémoire. Ne partage ni l’adresse de retour ni les clés.
4. Prépare le dossier. Dans **Dépôt**, demande la création du brouillon et confirme la boutique, la catégorie numérique et la période de fabrication acceptée par Etsy. L’envoi prend en charge les créations numériques réalisées par le vendeur et prêtes au téléchargement. Le prix doit être dans la devise de la boutique. Examine le brouillon dans Etsy avant toute activation.
5. Une activation réelle fait l’objet d’une confirmation distincte et peut entraîner les frais prévus par Etsy. En cas de réponse incertaine, ouvre **Rapprocher l’action**. Vérifie le résultat dans Etsy avant de confirmer une absence ou de fournir un identifiant. Les opérations réussies restent mémorisées afin de reprendre un transfert interrompu.

Le connecteur Etsy a des tests de transport simulés. L’autorisation d’une boutique réelle et la validation commerciale finale doivent être effectuées par son propriétaire. Les tests du projet ne publient rien.

## Importer une fiche produit avec un manifeste

Le schéma JSON complet est fourni dans [manifest.schema.json](manifest.schema.json) et par `/api/schema` dans l’application. [Exemple broché](examples/paper/produit.json) · [Exemple Etsy](examples/etsy/produit.json) · [Exemple Kindle](examples/kindle/produit.json).

Les attributs minimaux sont `schema_version` (valeur `1.0`), `title`, `kind`, `channel` et `version`. Le système crée un identifiant si `product_id` est omis. Conserve cet identifiant pour relier les éditions d’une même œuvre. Le triplet identifiant, canal, version est unique. La liste `expected` décrit les noms de fichiers et leurs rôles. Les champs inconnus et les noms incohérents sont rejetés. Une fiche importée démarre au brouillon et ses conclusions déclarées restent consultatives. Les contrôles sont exécutés sur les fichiers locaux.

Pour préparer une fiche complète à importer depuis la bibliothèque, donne cette consigne à l’équipe éditoriale.

> Prépare produit.json au format du schéma Venture Publisher joint. Conserve les noms exacts des fichiers, la langue, le prix et la version approuvés. Décris séparément tous les fichiers attendus, les contrôles effectivement réalisés et les validations humaines reçues. Indique unknown pour tout usage de l’IA qui doit être clarifié. Fournis le JSON en UTF-8. Joins le schéma et le dernier manifeste quand ils sont disponibles.

## Architecture et décisions

- Interface HTML, CSS et JavaScript servie sur la boucle locale par Python et FastAPI. Les opérations de préparation n’appellent aucun serveur externe.
- SQLite conserve les éditions et les instantanés. Les fichiers binaires restent sur disque, indexés par SHA-256. Les mutations vérifient le numéro de révision pour éviter les écrasements silencieux.
- `venture/workshop.py` assemble les missions et les décisions validées. `models.py` définit le manifeste, `quality.py` lit les fichiers et applique les règles, `store.py` gère l’intégrité et la sauvegarde, `etsy.py` isole le transport Etsy.
- KDP utilise le dépôt assisté. Les profils d’impression pris en charge sont explicites. La structure EPUB est contrôlée localement, le rendu typographique relève de Kindle Previewer. Le calcul du prix final et des redevances est à vérifier sur la plateforme.
- Fonctionnement mono-utilisateur. Par défaut le lanceur écoute exclusivement sur 127.0.0.1. Les mutations passent par l’interface locale et exigent un en-tête propre à l’application. L’API refuse les hôtes externes. Les secrets OAuth sont absents de SQLite, des exports et des sauvegardes.
- Les versions d’édition se dupliquent explicitement. Une édition déjà en dépôt est protégée contre les changements de fichiers et de métadonnées. Les instantanés permettent de récupérer les livrables enregistrés.
- Étapes d’intégration sur une installation réelle : vérifier le lanceur sur le poste cible, restaurer une sauvegarde sur un autre emplacement et connecter la boutique autorisée si souhaité.

## Vérifier

Depuis l’environnement Python contenant les dépendances :

```sh
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m pip install playwright
python -m playwright install chromium
python tests/desktop.py
```

Les tests utilisent un catalogue temporaire et des transports Etsy simulés. Le test navigateur ouvre le serveur par son lanceur et contrôle le parcours utilisateur. Les exemples contiennent uniquement des données fictives. Les polices incorporées aux PDF utilisent DejaVu, dont l’avis de licence figure dans [examples/FONTS-LICENSE.txt](examples/FONTS-LICENSE.txt).

## Règles de plateforme

Les limites et endpoints peuvent évoluer. Les bases documentaires utilisées sont le [guide Etsy des fichiers numériques](https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings), les [annonces Etsy v3](https://developers.etsy.com/documentation/tutorials/listings/), [OAuth Etsy](https://developers.etsy.com/documentation/essentials/authentication/), les [dimensions et marges KDP](https://kdp.amazon.com/en_US/help/topic/GVBQ3CMEQW3W2VL6), les [couvertures KDP](https://kdp.amazon.com/en_US/help/topic/G201953020) et les [règles de contenu KDP](https://kdp.amazon.com/en_US/help/topic/G200672390).
