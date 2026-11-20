# Synchronisation Google Sheets et migrations automatiques

## 1. Ce que fait la chaîne

| Commande | Rôle |
|---|---|
| `manage.py migrer` | Copie `db.sqlite3` dans `backups/` **seulement si** une migration attend, puis applique les migrations sans poser de question. |
| `manage.py etat_google` | Affiche le compte de service et vérifie l'accès à chaque feuille sans télécharger de classeur. |
| `manage.py synchroniser_classeurs` | Télécharge les feuilles Google, classe chaque classeur, produit le rapport d'analyse. **N'écrit rien en base.** |
| `manage.py synchroniser_classeurs --ecrire` | En plus : copie la base avant les importeurs, la retire si rien n'a changé, puis lance les importeurs reconnus (formations, élèves, journal de caisse). |
| `.\demarrer.ps1` | `migrer` puis `runserver` : le serveur ne démarre plus sur un schéma en retard. |
| `.\synchroniser.ps1` | `migrer` puis `synchroniser_classeurs --ecrire`, journalisé dans `synchronisation.log`. Point d'entrée de la tâche planifiée. |
| `.\installer_tache_synchronisation.ps1` | Installe ou retire la tâche Windows qui appelle `synchroniser.ps1` toutes les heures. |
| Bouton « Synchroniser les classeurs » | Depuis le tableau de bord super administrateur, ouvre une page de chargement dédiée qui lance la même commande en écriture, avec verrou anti-chevauchement, message de résultat et trace d'audit. |
| `deploy/pythonanywhere_sync.py` | Point d'entrée quotidien de l'ordonnanceur PythonAnywhere ; lance l'import en écriture après 72 heures depuis la dernière réussite. |

Les feuilles configurées par défaut sont les deux classeurs du bureau :

- `1skjUY883GPpTOlG9nYP_Z6PrAj60rQ47NvTfpRYygCU`
- `1GmjRV7T1dcLCD9kQd_hphdYLrO1Z6ezfgwd9xIA41gU`

On les remplace sans toucher au code :

```powershell
# une fois par session
$env:CLASSEURS_GOOGLE_IDS = "id1,id2"
# ou à chaque appel
.\.venv\Scripts\python.exe manage.py synchroniser_classeurs --feuille id1 --feuille id2
```

## 2. Accès aux feuilles

Google refuse (HTTP 401) toute feuille privée lue sans authentification. Deux
voies sont possibles ; la seconde est la seule à conseiller pour des données
d'élèves et de caisse.

### A. Feuille publique en lecture

Dans chaque feuille : **Partager → Accès général → Tout utilisateur disposant
du lien → Lecteur**.

C'est le plus rapide, mais **toute personne qui possède le lien lit les noms,
téléphones et montants**. À réserver à des classeurs de démonstration.

### B. Compte de service (recommandé)

Un compte de service est un robot Google, pas une boîte Gmail. Il possède sa
propre adresse `...@....iam.gserviceaccount.com` ; c'est cette adresse qu'on
partage avec les feuilles, pas `universacademy70@gmail.com`.

1. Ouvrir <https://console.cloud.google.com/> et créer un projet (par exemple
   `academy-sync`).
2. Dans **API et services → Bibliothèque**, activer **Google Drive API** et
   **Google Sheets API** pour ce projet.
3. Dans **IAM et administration → Comptes de service**, créer un compte de
   service nommé par exemple `academy-sync`.
4. Ouvrir ce compte, onglet **Clés → Ajouter une clé → Créer une clé → JSON**.
   Le navigateur télécharge un fichier `.json`.
5. Déposer ce fichier ici, en le renommant `service-account.json` :

   ```
   C:\Users\<vous>\.config\academy\service-account.json
   ```

   Le dossier peut être créé au besoin :

   ```powershell
   New-Item -ItemType Directory -Force "$HOME\.config\academy" | Out-Null
   ```

   Ce chemin est hors du dépôt et `.gitignore` bloque aussi
   `service-account*.json`.
6. Ouvrir le JSON avec un éditeur et copier la valeur de `client_email`.
7. Dans chaque Google Sheet : **Partager**, coller ce `client_email`, rôle
   **Lecteur**. Décocher la notification si Google la propose.
8. Vérifier sans rien télécharger :

   ```powershell
   .\.venv\Scripts\python.exe manage.py etat_google
   ```

   La commande affiche le `client_email` à partager, puis pour chaque feuille
   si l'accès public, l'API Drive et l'API Sheets répondent. Elle sort en
   erreur tant qu'une feuille reste inaccessible.

Si l'API Drive est activée, le fichier reçu est le vrai `.xlsx` ; sinon la
synchronisation retombe sur l'API Sheets (les dates y arrivent en texte
affiché). Si les feuilles appartiennent à un domaine Google Workspace, son
administrateur peut interdire le partage avec un compte externe : il faut
alors autoriser ce partage ou utiliser une feuille publique de démonstration.

## 3. Utilisation

```powershell
# Diagnostic d'accès, sans téléchargement
.\.venv\Scripts\python.exe manage.py etat_google

# Prévisualisation : télécharge et analyse, aucune écriture
.\.venv\Scripts\python.exe manage.py synchroniser_classeurs

# Écriture, après lecture du rapport
.\.venv\Scripts\python.exe manage.py synchroniser_classeurs --ecrire

# Forcer le type d'importeur
... --ecrire --importer journal
... --ecrire --importer etudiants --efface
```

Le classement est volontairement prudent :

- `Base Etudiants` → classeur des élèves (`importer_etudiants`) ;
- onglet `Enregistrement_Opérations` ou `Feuille 2` → journal de caisse
  (`importer_feuille`) ;
- tout le reste → `inconnu`, signalé sans être importé.

Les fichiers sont reçus dans `docs/donnees/import_<date>/` (dossier ignoré par
git) et le rapport dans `RAPPORT_ANALYSE.md` du même dossier. Au passage
suivant, les classeurs et le rapport précédents sont rangés dans
`docs/donnees/import_<date>/archive/<horodatage>/`.

Sur `--ecrire`, une copie de `db.sqlite3` est posée dans `backups/` **avant**
les importeurs. Si aucun importeur n'a réellement modifié la base, la copie est
retirée : une tâche horaire ne remplit pas `backups/` de copies identiques. En
cas d'échec ou d'écriture réelle, elle reste en place.

## 4. Temps réel et tâche horaire

Google Sheets n'a pas de notification vers cette application : « temps réel »
veut dire **relire à intervalle court**. Chaque passage télécharge l'état
courant des feuilles et l'importe ; la fraîcheur est celle de la tâche
planifiée. Une fois par heure est un bon compromis pour ce bureau : les
données sont rafraîchies sans multiplier les requêtes Google.

L'application ne va pas chercher Google à chaque page : une panne réseau ou un
quota Google ne doit pas bloquer le guichet. La base reste la source de
service, la synchronisation la rafraîchit.

### Installer la tâche

```powershell
# 1. Première installation en prévisualisation : télécharge et analyse,
#    n'écrit rien en base.
.\installer_tache_synchronisation.ps1 -SansEcrire

# 2. Après lecture du rapport d'analyse, passer en écriture.
.\installer_tache_synchronisation.ps1
```

Chaque appel remplace la tâche précédente (`-Force`) et lance un passage
immédiat. Pour différer, ajouter `-SansExecution`.

> Si PowerShell refuse d'exécuter les scripts (`about_Execution_Policies`),
> préfixer l'appel ainsi :
>
> ```powershell
> powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\installer_tache_synchronisation.ps1
> ```
>
> La tâche planifiée, elle, utilise déjà `-ExecutionPolicy Bypass`.

Autres options :

```powershell
# Choisir l'heure du premier passage
.\installer_tache_synchronisation.ps1 -Heure 07:30

# JSON du compte de service à un autre emplacement
.\installer_tache_synchronisation.ps1 -Credentials D:\secrets\academy.json
```

La tâche est nommée **UniversAcademy - Synchronisation** et tourne sous
l'utilisateur courant. Elle est visible dans `taskschd.msc`. Le script refuse
les lancements simultanés (`-MultipleInstances IgnoreNew` côté Windows et
verrou interne côté PowerShell) et s'arrête au bout de 50 minutes pour ne pas
rester bloquée.

La tâche s'exécute lorsque la session de cet utilisateur est ouverte : c'est
ce qui donne accès au JSON stocké dans son profil. Pour un serveur sans
session ouverte, il faut enregistrer la tâche avec un compte de service
Windows et son mot de passe, puis placer le JSON dans un dossier lisible par
ce compte.

### Retirer la tâche

```powershell
.\installer_tache_synchronisation.ps1 -Desinstaller
```

### Vérifier la tâche

```powershell
Get-ScheduledTaskInfo -TaskName "UniversAcademy - Synchronisation" |
  Select-Object LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult` vaut `0` quand le dernier passage s'est terminé correctement.
Un avertissement « compte de service absent » dans le journal n'empêche pas la
synchronisation des feuilles publiques ; le détail est toujours dans
`synchronisation.log`.

### Équivalent manuel

Si tu préfères `schtasks` :

```powershell
schtasks /Create /TN "UniversAcademy - Synchronisation" /SC HOURLY /MO 1 /ST 07:30 `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"D:\Dev\01_Professionnel\Django\academy\synchroniser.ps1\"" `
  /F
schtasks /Run /TN "UniversAcademy - Synchronisation"
```

### Journal et comportement

- Journal : `synchronisation.log` à la racine du projet. Au-delà de 5 Mo, il
  est renommé `synchronisation.log.1` (un seul fichier d'archive).
- Sans compte de service, `synchroniser.ps1` journalise « Compte de service
  absent » puis tente l'export public des feuilles : elles doivent être
  partagées en lecture. Une feuille privée fait échouer la commande avec un
  code non nul et le détail dans le journal.
- Un échec réel (réseau, partage retiré, import en conflit) laisse un code de
  sortie non nul et le détail dans le journal.
- Pour un passage en lecture seule : `.\synchroniser.ps1 -SansEcrire`.
- Pour un JSON à un autre emplacement :
  `.\synchroniser.ps1 -Credentials D:\secrets\academy.json`, ou la variable
  d'environnement `GOOGLE_APPLICATION_CREDENTIALS`.

> Un import qui entre en conflit avec une saisie faite dans l'application
> s'arrête : `importer_etudiants` refuse d'écraser sans `--efface`. La tâche
> journalise l'échec, elle ne force rien.

## 5. Migrations automatiques

`migrer` est idempotent : sans migration en attente, il ne change rien et ne
crée pas de copie — une tâche qui l'appelle toutes les heures ne remplit donc
pas `backups/`. Dès qu'une migration attend, la copie SQLite est posée avant
`migrate`. Il est appelé par `demarrer.ps1` et `synchroniser.ps1`, donc un
poste démarré ou une tâche exécutée ne peut plus travailler sur une base en
retard.

```powershell
.\.venv\Scripts\python.exe manage.py migrer --verifier
```

`--verifier` ajoute `check` et `makemigrations --check --dry-run` : la commande
échoue si du code attend une migration qui n'a pas été générée. C'est le
contrôle à mettre dans une chaîne de déploiement.

La sauvegarde avant migration est faite pour SQLite. Sur PostgreSQL, elle reste
à la charge de l'exploitation (`pg_dump`), et la commande le rappelle.
