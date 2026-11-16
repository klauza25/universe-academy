# Prompt de conception — Univers Academy

> **But du document.** Ce fichier contient un prompt complet, réutilisable tel quel, pour faire concevoir et réaliser la plateforme **Univers Academy** par un agent de codage (Claude Code, Codex, Cursor, Copilot Workspace, etc.) ou par un développeur qui reprend le projet.
>
> Il est aligné sur le code et la base au 10/11/2026. Le document de référence fonctionnel reste `docs/CAHIER_DES_CHARGES.md` : en cas de doute, c'est lui qui tranche.

---

## 0. Comment utiliser ce prompt

1. Copier tout ce document (à partir de la section 1) dans la conversation de l'agent.
2. Laisser l'agent produire d'abord la **restitution de conception** de la phase 0, sans écrire de code.
3. Valider ou corriger cette restitution.
4. Enchaîner les phases 1 à 6, avec un point de contrôle à chaque fin de phase.
5. Exiger à chaque étape : `manage.py check`, `manage.py test core.tests`, et un compte rendu court de ce qui a changé.

Le prompt est volontairement prescriptif. Il décrit le résultat attendu, pas seulement les technologies. L'agent doit **livrer un produit qui fonctionne**, pas une maquette.

---

## 1. Rôle et mission

Tu es **développeur Django senior**, spécialisé dans les applications de gestion métier, la sécurité applicative et les interfaces sobres. Tu travailles en français, dans un contexte de centre de formation professionnelle.

**Mission** : concevoir et réaliser une application web de gestion complète pour **Univers Academy**, un centre de formation à Brazzaville (République du Congo). L'application couvre :

- le portail public et les candidatures aux bourses ;
- l'accueil, les visites et les prospects ;
- le secrétariat : étudiants, inscriptions, documents ;
- la pédagogie : catalogue, modules, leçons, groupes, séances, présences, cahier de texte, ressources ;
- la comptabilité : caisse multi-comptes, journal, clôtures, paiements et reçus ;
- les réglages : établissement, années académiques, permissions ;
- l'administration : comptes, rôles, audit, supervision ;
- la synchronisation horaire de deux classeurs Google Sheets privés vers la base.

L'application est **mono-établissement**, en **français**, et sert une équipe d'une dizaine de postes et plusieurs centaines d'étudiants.

---

## 2. Règles absolues (le non-négociable)

Ces règles passent avant toute préférence d'implémentation. Si une demande utilisateur les contredit, tu le signales et tu proposes une alternative.

1. **Aucune autorisation côté client uniquement.** Chaque écran, chaque action et chaque export est contrôlé côté serveur. Masquer un bouton ne protège rien.
2. **Pas d'authentification externe.** Authentification locale Django (e-mail ou code interne + mot de passe). Pas de Clerk, pas d'OAuth social.
3. **Interface en français.** Les chaînes visibles sont traduisibles (`gettext`), l'anglais reste disponible par le sélecteur de langue. Aucun mélange de langues au rendu.
4. **Aucune suppression destructive** d'une donnée référencée : on archive, on annule, on désactive. Les documents et pièces restent consultables.
5. **Toute écriture automatisée est précédée d'une sauvegarde** de la base. Une écriture qui n'a rien changé ne laisse pas de sauvegarde.
6. **Les migrations restent automatiques** : `manage.py migrer` sauvegarde seulement si une migration est réellement en attente, puis applique. Une tâche horaire ne doit pas remplir `backups/`.
7. **L'application ne réécrit jamais dans Google.** Les classeurs sont une source d'alimentation ; la base est la source de service.
8. **Aucune donnée réelle dans les tests.** Les tests utilisent la base de test Django. La base de production n'est jamais touchée.
9. **Pas de secret dans le dépôt.** Clés, mots de passe, JSON de compte de service : hors dépôt, via variables d'environnement ou fichier utilisateur.
10. **Pas de fonctionnalité silencieuse.** Toute action sensible laisse une ligne d'audit : acteur, action, entité, résumé avant/après, IP, horodatage.
11. **Pas de régression fonctionnelle.** Avant de livrer, `manage.py check` doit être propre et la suite `manage.py test core.tests` doit passer intégralement.
12. **Pas de dépendance non déclarée.** Toute bibliothèque ajoutée entre dans `requirements.txt` avec une version minimale.

---

## 3. Contexte et problème à résoudre

Le centre gère aujourd'hui ses étudiants, ses inscriptions, sa caisse et sa pédagogie dans des classeurs Google tenus à la main. Les conséquences sont connues :

- doubles saisies et erreurs de recopie ;
- soldes et reçus calculés à la main ;
- aucune trace fiable de qui a modifié quoi ;
- impossibilité de savoir, à un instant donné, où en est un étudiant dans son parcours ;
- dépendance à une seule personne qui connaît les fichiers.

La plateforme doit remplacer ces classeurs pour le travail quotidien, tout en continuant à les **lire** automatiquement, une fois par heure, tant que l'équipe continue d'y saisir certaines informations.

**Résultats attendus** : une base unique et cohérente, des droits par poste, des soldes justes, des documents centralisés, une pédagogie suivie séance par séance, et une synchronisation traçable.

---

## 4. Périmètre

### 4.1 Dans le périmètre

- Portail public : présentation, formations, inscription, demande d'accès, candidature bourse et suivi.
- Back-office par rôle, avec tableaux de bord et files de travail.
- Gestion complète des étudiants, inscriptions, documents et certificats.
- Catalogue de formations, modules et leçons ; groupes, séances, présences, cahier de texte, ressources.
- Caisse multi-comptes, journal des opérations, transferts, clôtures, paiements étudiants, reçus imprimables.
- Bourses : candidature publique, instruction, décision.
- Réglages de l'établissement et années académiques.
- Comptes, rôles, 19 permissions fines, journal d'audit.
- Synchronisation Google Sheets horaire, avec sauvegarde et rapport d'analyse.
- Documentation d'exploitation et de recette.

### 4.2 Hors périmètre de la version de référence

- Comptabilité générale normalisée (plan comptable, balance, TVA).
- Paie, gestion des ressources humaines, immobilisations.
- Messagerie interne temps réel, visioconférence.
- Application mobile native.
- Paiement en ligne par carte ou agrégateur.
- Réécriture des classeurs Google depuis l'application.
- Multi-établissement et multi-devise avec conversion.

Tout ajout hors périmètre doit être discuté, estimé et documenté avant développement.

---

## 5. Pile technique et arborescence imposées

### 5.1 Pile

| Élément | Choix |
|---|---|
| Langage | Python 3 |
| Framework | Django 5.2 (`Django>=5.1,<6.0`) |
| Base | SQLite `data/db.sqlite3` en développement ; PostgreSQL via `DATABASE_URL` |
| Styles | Tailwind CSS compilé vers `static/css/output.css` |
| Fichiers | `Pillow`, `django-cleanup`, stockage privé sous `media/private/` |
| Imports | `openpyxl` pour les classeurs |
| Google | `google-auth` + `requests` (compte de service) |
| Traductions | `polib`, `locale/fr` et `locale/en` |
| Documents | `python-docx` pour les livrables Word du dossier `docs/` |
| Config | `python-dotenv`, `dj-database-url` |

### 5.2 Arborescence cible

```text
academy/
├── manage.py
├── requirements.txt
├── .env.example
├── demarrer.ps1
├── synchroniser.ps1
├── installer_tache_synchronisation.ps1
├── univers_academy/          # settings, urls, wsgi
├── core/
│   ├── models.py             # 37 modèles, contraintes, gardes
│   ├── forms.py              # formulaires et validation métier
│   ├── decorators.py         # autorisations serveur
│   ├── middleware.py         # statut de compte
│   ├── urls.py               # routes publiques, bourses, dashboard
│   ├── views.py              # portail, comptes, audit, documents
│   ├── views_accueil.py
│   ├── views_secretariat.py
│   ├── views_pedagogie.py
│   ├── views_comptabilite.py
│   ├── views_reglages.py
│   ├── views_supervision.py
│   ├── views_profile.py
│   ├── caisse.py             # service d'écriture de caisse
│   ├── parametres.py
│   ├── annee_academique.py
│   ├── taches.py
│   ├── relations.py          # 16 contrôles de cohérence
│   ├── sauvegarde.py
│   ├── google_sheets.py
│   ├── *_import.py           # élèves, feuille de caisse, formations
│   ├── management/commands/  # 19 commandes d'exploitation
│   ├── migrations/
│   └── tests/                # suite par domaine
├── templates/                # 109 gabarits : public, dashboard, bourses, impressions
├── static/                   # Tailwind compilé, JS, icônes
├── locale/                   # fr, en
├── media/                    # privé et avatars
├── backups/                  # copies SQLite
├── docs/                     # cahier des charges, exploitation, rapports
└── data/db.sqlite3
```

Contraintes de structure :

- Une vue par domaine, pas un fichier `views.py` de 10 000 lignes.
- Les règles métier lourdes vivent dans des services (`caisse.py`, `parametres.py`, `relations.py`, `sauvegarde.py`), pas dans les templates.
- Les gabarits partagent une base unique (`templates/base.html`) et des partiels par domaine.
- Les noms de routes sont stables et explicites (`core:dashboard:module-create`, etc.).

---

## 6. Acteurs, rôles et autorisations

### 6.1 Statuts de compte

| Statut | Effet |
|---|---|
| `PENDING_APPROVAL` | Compte créé, aucun accès métier ; redirigé vers la complétion de sa demande d'accès. |
| `ACTIVE` | Accès selon les rôles. |
| `SUSPENDED` | Accès bloqué, y compris sur une session déjà ouverte. |
| `DISABLED` | Accès bloqué ; `disabled_at` renseigné. |
| `REJECTED` | Demande refusée ; accès bloqué. |

Le statut est contrôlé à **chaque requête** par un middleware, sauf pages publiques, fichiers statiques, admin Django et documents privés servis par leur vue dédiée.

### 6.2 Rôles

Huit rôles actifs. Deux anciens postes (`COMPTABLE`, `ACCUEIL`) restent en base pour l'historique mais ne sont **plus attribuables** et n'ont plus de menu.

| Rôle | Mission | Tableau de bord | Préfixe de code |
|---|---|---|---|
| `SUPER_ADMIN` | Administration technique, comptes, rôles, audit, supervision, caisse. | `/dashboard/super-admin/` | `UA-ADM` |
| `ADMIN` | Lecture transversale, caisse, demandes d'accès, bourses. | `/dashboard/admin/` | `UA-ADM` |
| `DIRECTION` | Pilotage, validation des inscriptions, catalogue, réglages, années. | `/dashboard/direction/` | `UA-DIR` |
| `ASSISTANT_ADMIN` | Assistance administrative et comptable. | `/dashboard/comptabilite/` | `UA-ASY` |
| `SECRETAIRE` | Dossiers étudiants, inscriptions au guichet, documents. | `/dashboard/secretaire/` | `UA-SEC` |
| `RESP_PEDA` | Catalogue, modules, leçons, groupes, séances, ressources, validation pédagogique. | `/dashboard/responsable-pedagogique/` | `UA-RPD` |
| `FORMATEUR` | Groupes affectés, séances, présences, cahier de texte, ressources. | `/dashboard/formateur/` | `UA-FRM` |
| `ETUDIANT` | Ressources publiées, présences, fiches, espace personnel. | `/dashboard/etudiant/` | `UA-ETU` |

### 6.3 Règles transversales

1. `SUPER_ADMIN` et `ADMIN` lisent tous les modules mais **n'écrivent pas le métier courant** (visites, prospects, étudiants, inscriptions à la création, présences, séances, ressources, modules, leçons).
2. **Exception caisse et paiements** : les rôles transversaux peuvent opérer la caisse (opération, annulation, correction, paiement étudiant, clôture, compte, catégorie), avec audit.
3. **Exception groupes** : création et modification d'un groupe ouvertes à `RESP_PEDA`, `DIRECTION`, `SUPER_ADMIN`, `ADMIN` par la route dédiée.
4. **Exception inscription existante** : modification d'une inscription ouverte à `SECRETAIRE`, `DIRECTION`, `SUPER_ADMIN`, `ADMIN`, avec audit `ENROLLMENT_EDIT`.
5. **Actes réservés au `SUPER_ADMIN`** : création/modification de compte, attribution ou retrait de rôle, changement de statut, matrice des permissions, décision finale de bourse.
6. **Auto-modification interdite** : personne ne modifie ses propres rôles ni son statut (403).
7. **Dernier super administrateur protégé** : retirer le rôle au dernier `SUPER_ADMIN` actif est refusé.
8. **Périmètre formateur** : un formateur ne voit que les groupes où il est affecté, leurs séances, présences et cahiers de texte ; il ne peut pas écrire dans les groupes des autres.
9. **Validation d'inscription** : `DIRECTION`, `ASSISTANT_ADMIN`, `RESP_PEDA`, `SUPER_ADMIN`. `ADMIN` reste en consultation.
10. **Demandes d'accès** : examen par `SUPER_ADMIN`, `ADMIN`, `RESP_PEDA`, `DIRECTION`, `ASSISTANT_ADMIN`, `SECRETAIRE`. `RESP_PEDA` n'attribue que `FORMATEUR` et `ETUDIANT` ; direction, assistant et secrétariat n'attribuent que `ETUDIANT` ; les rôles transversaux peuvent attribuer tous les rôles demandables (`ETUDIANT`, `FORMATEUR`, `SECRETAIRE`, `ASSISTANT_ADMIN`, `RESP_PEDA`).

### 6.4 Matrice de synthèse des accès

| Module | SUPER_ADMIN | ADMIN | DIRECTION | ASSISTANT_ADMIN | SECRETAIRE | RESP_PEDA | FORMATEUR | ETUDIANT |
|---|---|---|---|---|---|---|---|---|
| Visites / prospects | Lecture | Lecture | Écriture | Écriture | Écriture | — | — | — |
| Dossiers étudiants | Lecture | Lecture | Écriture | Lecture | Écriture | — | — | Son dossier |
| Inscriptions | Lecture + édition + validation | Lecture + édition | Création + édition + validation | Écriture + validation | Création + édition | Validation | — | — |
| Paiements | Écriture | Écriture | Écriture | Écriture | Écriture | — | — | — |
| Caisse, clôtures | Écriture | Écriture | Écriture | Écriture | Écriture | — | — | — |
| Catalogue, modules, leçons | Lecture | Lecture | Écriture | Lecture | Lecture | Écriture | Écriture | Lecture |
| Groupes | Écriture | Écriture | Écriture | Lecture | Lecture | Écriture | Ses groupes | — |
| Séances, présences, cahier de texte | Lecture | Lecture | Écriture | Lecture | Lecture | Écriture | Ses groupes | Ses présences |
| Ressources | Lecture | Lecture | Écriture | Lecture | Lecture | Écriture | Écriture | Publiées |
| Bourses | Décision | Lecture | Instruction | Instruction | Instruction | Instruction | — | Sa candidature |
| Réglages, années | Écriture | Lecture | Écriture | Lecture | Lecture | Lecture | — | — |
| Comptes, rôles | Écriture | Lecture | Lecture | — | — | — | — | — |
| Audit, supervision | Lecture | Lecture | Lecture | Lecture | — | Lecture | — | — |

La matrice fine à 19 droits est éditable par le `SUPER_ADMIN` dans `/dashboard/super-admin/permissions/`.

### 6.5 Contrôle d'accès attendu dans le code

- Décorateurs : `role_required`, `business_write_required`, `cash_write_required`, `payment_write_required`, `permission_required`, `super_admin_required`, `enrollment_validation_required`.
- Refus par HTTP 403 explicite, jamais par une redirection silencieuse ni par un simple masquage.
- `payment_write_required` lit la permission `finance.write` : un super administrateur peut l'accorder poste par poste.
- Les rôles transversaux sont traités par `is_elevated` (`SUPER_ADMIN`, `ADMIN`).
- Le périmètre formateur est filtré dans les requêtes (`session__formateurs=user`), pas seulement à l'affichage.

---

## 7. Exigences fonctionnelles

Les identifiants `PF-`, `SE-`, `PE-`, `PG-`, `PR-`, `CO-`, `BO-`, `RG-`, `UT-` sont ceux du cahier des charges. Chaque exigence doit être couverte par un test automatisé ou une recette manuelle documentée.

### 7.1 Portail public et accès

- Accueil public, présentation, formations actives, contact, sélecteur de langue et de thème.
- Inscription publique : création d'un compte en `PENDING_APPROVAL` et d'une demande d'accès ; **aucun rôle attribué automatiquement**.
- Connexion par e-mail **ou** code interne, plus mot de passe.
- Demande d'accès complémentaire pour un compte en attente.
- Mot de passe oublié, changement d'e-mail par jeton signé, déconnexion.
- Refus explicite si un rôle élevé est demandé depuis le formulaire public.
- Bandeau de langues français/anglais, thème clair/sombre persistant.

**Critère** : un visiteur qui s'inscrit comme formateur obtient un compte en attente, une demande enregistrée, aucun rôle, et aucun accès au back-office.

### 7.2 Tableaux de bord et files de travail

- Un tableau de bord par rôle, alimenté par une source unique de compteurs.
- Files : demandes d'accès, inscriptions à valider, recouvrements, formateurs, formations actives, notifications non lues.
- Les rôles transversaux voient toutes les files ; les autres voient leur périmètre.
- Compteurs bornés par année académique quand le filtre existe.

### 7.3 Accueil, visites et prospects

- Enregistrer une visite : contact, type de visiteur, motif, service et personne hôtes, heure d'arrivée, agent.
- Réutiliser un contact existant ou en créer un.
- Enregistrer le départ ; convertir une visite en prospect.
- Gérer les motifs de visite (libellé, ordre, actif/inactif).
- Prospect : référence `PRO-AAAA-NNNN`, formation visée, domaine, niveau, programme linguistique, contact préféré, statut, prochaine relance.
- Suivi de prospect : contact, résumé, information donnée, résultat, prochaine action et date.
- Historique d'audit par visite et par prospect.
- Conversion prospect → étudiant par le secrétariat.

### 7.4 Secrétariat : étudiants, inscriptions, documents

- Créer un étudiant (identité, contacts, naissance) avec mot de passe initial facultatif.
- Générer un code interne unique par rôle (`UA-ETU-0001`, etc.).
- Modifier un profil, poser une photo, changer de mot de passe.
- Déposer des documents (identité, diplôme, relevé, photo, certificat, autre), éventuellement liés à une inscription ; remplacer un fichier supprime l'ancien.
- Créer une inscription : étudiant, groupe, tarif, remise, plan de paiement, notes.
- Calculer `net = tarif − remise` ; refuser une remise supérieure au tarif.
- Refuser deux inscriptions identiques (même étudiant, même groupe).
- Valider une inscription : active le compte étudiant en attente, rattache le groupe, audite `ENROLLMENT_VALIDATE`.
- Signaler un compte étudiant actif sans aucun dossier d'inscription.
- Filtrer les listes par année académique.
- Servir les documents privés uniquement par une vue authentifiée.

### 7.5 Pédagogie : catalogue, modules et leçons

- Lister les formations avec leurs modules et leçons.
- Créer, modifier, archiver et réactiver une formation.
- **Créer un module manuellement** depuis l'écran « Programmes », sans fenêtre modale ni JavaScript obligatoire.
- **Créer une leçon manuellement** sous un module.
- Modifier un module et une leçon existants.
- Afficher modules et leçons dans l'ordre défini, avec leurs heures prévues.
- Auditer chaque création, modification, archivage et réactivation.
- Les rôles transversaux consultent seulement.

**Exigence détaillée — création d'un module**

1. Le responsable pédagogique ouvre `/dashboard/pedagogie/programmes/`.
2. Il repère la formation concernée (ancre `#formation-<id>`).
3. Il déplie le formulaire natif `<details>` placé sous la formation.
4. Il saisit le titre ; la formation est préremplie ; l'ordre et les heures sont facultatifs.
5. À défaut, l'ordre prend la place suivante dans la formation et les heures valent 0.
6. Il valide : le module apparaît, l'ancre est conservée, l'audit `MODULE_CREATE` est écrit.

**Exigence détaillée — création d'une leçon**

Même mécanisme sous chaque module, avec l'ancre `#module-<id>` et l'audit `LESSON_CREATE`.

**Rôles** : création et modification ouvertes à `FORMATEUR`, `RESP_PEDA`, `DIRECTION` ; les rôles transversaux sont refusés en écriture mais voient le catalogue.

**Critère** : un `ADMIN` qui tente de créer un module reçoit 403 et ne voit pas le formulaire.

### 7.6 Pédagogie : groupes, séances, présences, cahier de texte

- Créer un groupe : formation, nom, période, emploi du temps, capacité, statut, formateurs.
- Refuser une date de fin antérieure ou égale à la date de début.
- Affecter un ou plusieurs formateurs ; un formateur ne voit que ses groupes.
- Séance : module, leçon, date, heures prévues et réelles, thème, objectifs, contenu, exercices, difficultés, statut.
- Feuille de présence : présent, absent, retard, heure d'arrivée, motif, note.
- Une seule présence par inscription et par date ; une seconde saisie le même jour est ignorée et la ligne d'origine conservée.
- Cahier de texte imprimable par groupe.
- Progression : volume traité par rapport au volume du catalogue.
- Fiche de cours étudiant : notions retenues, difficultés, observations, présence, heures suivies.
- Empêcher deux fiches pour la même inscription et la même séance.
- Vérifier que les heures suivies sont cohérentes (début avant fin).
- Feuille de suivi imprimable par étudiant.

### 7.7 Pédagogie : ressources et espace étudiant

- Créer une ressource : titre, description, formation/module/leçon/séance, type, fichier **ou** contenu HTML, échéance, statut.
- Exiger au moins un fichier ou un contenu HTML.
- Refuser un fichier de plus de 10 Mo et les extensions non autorisées.
- Publier une ressource aux étudiants de ses formations/groupes ; empêcher l'accès par URL directe.
- Retour étudiant : note 1–5 et commentaire, unique par ressource.
- Le formateur lit les retours de ses ressources.
- Espace étudiant : ressources publiées, présences, fiches de cours, feuille de suivi.

### 7.8 Comptabilité et caisse

- Journal filtrable (date, type, catégorie, caisse, moyen, auteur, période) et paginé.
- Exporter la sélection en CSV avec trace d'audit.
- Créer une opération : date, caisse, catégorie, libellé, montant, moyen, pièce, statut.
- Transfert entre deux caisses, avec caisse de destination, refus si identique.
- Refuser une écriture validée datée après aujourd'hui.
- Calculer le solde par caisse et refuser une sortie qui passe sous le plancher (− découvert autorisé), y compris par script.
- Les brouillons ne comptent pas dans le solde.
- Alerter sur une sortie qui consomme au moins le seuil paramétré du disponible.
- Administrer une caisse : nom, type, devise, solde d'ouverture, découvert autorisé, archivage, caisse de remplacement.
- Refuser toute écriture sur une caisse archivée.
- Gérer les catégories (nom, sens, actif) ; désactivation plutôt que suppression si utilisée.
- Annuler une opération avec motif ; conserver la ligne annulée et l'audit.
- Clôture : solde d'ouverture, théorique, compté, écart, note ; une seule clôture par caisse et par jour.
- Paiement étudiant : inscription, montant, moyen, mois réglé, date d'encaissement, note.
- Empêcher le double encaissement (clé de soumission).
- Générer une référence `PAY-AAAA....`.
- Refuser un paiement daté après aujourd'hui et un montant supérieur au reste à payer.
- Générer un reçu imprimable portant l'identité de l'établissement.
- Ne jamais additionner paiements et écritures de caisse : ce sont deux vues du même argent.
- Superviser : soldes, répartition par catégorie, export CSV.
- Corriger une écriture (motif) en conservant l'écriture remplacée.
- Refuser la correction d'une écriture annulée.
- Contrôles `verifier_relations` (16) et `audit_finances` en lecture seule.

### 7.9 Bourses

- Formulaire public : identité, coordonnées, destination, programme, domaine d'études, motivation.
- Générer une référence unique `BRS-AAAA-NNNN` et un jeton de suivi.
- Suivre une candidature par sa référence, sans compte.
- Statuts : soumise, en instruction, acceptée, rejetée, retirée.
- Une seule candidature active par personne et par destination.
- Auditer la décision.
- Gérer les destinations proposées.
- L'écran d'instruction est partagé ; la décision finale reste au `SUPER_ADMIN`.

### 7.10 Réglages et années académiques

- Régler l'établissement : nom, signature, adresse, téléphone, e-mail, RCCM, NIU, CNSS, devise, seuil d'alerte.
- Une seule ligne de réglages, créée à la première lecture avec des valeurs neutres.
- La devise n'est jamais codée en dur : elle vient des réglages.
- Année académique : libellé unique, début, fin, une seule année « en cours » à la fois.
- Refuser une fin antérieure au début, à l'écran et en base.
- Filtrer groupes, étudiants, inscriptions et paiements par année.
- Historiser les modifications des réglages (avant/après) dans l'audit.

### 7.11 Utilisateurs, rôles, permissions, audit

- Lister, rechercher et filtrer les comptes.
- Créer un compte, le modifier, poser sa photo (**super administrateur**).
- Attribuer ou retirer un rôle, changer le statut d'accès depuis la fiche utilisateur.
- Interdire l'auto-modification des rôles et du statut.
- Protéger le dernier super administrateur actif.
- Éditer la matrice des 19 permissions par rôle, case par case.
- Journal d'audit filtrable (acteur, action, entité, date) avec pagination.
- Notifications : création, marquage lu, compteur, interrogation périodique.

---

## 8. Règles de gestion critiques

Ces règles doivent être appliquées **en base** quand c'est possible, et **dans les services** dans tous les cas. Un test doit les couvrir.

1. `net_amount = tariff_amount − discount_amount`, avec `0 ≤ discount ≤ tariff`.
2. `reste à payer = net_amount − somme des paiements validés`, jamais négatif.
3. Une inscription unique par couple `(étudiant, groupe)`.
4. Une présence unique par couple `(inscription, date)`.
5. Une fiche de cours unique par couple `(inscription, séance)`.
6. Une séance unique par `(groupe, date, heure de début prévue)`.
7. Une clôture unique par `(caisse, date)`.
8. Une seule année académique `is_current = True`.
9. Un transfert de caisse ne peut pas viser la même caisse.
10. Le solde d'une caisse ne peut pas descendre sous `−overdraft_limit`.
11. Une opération ou un paiement validé ne peut pas être daté dans le futur.
12. Une écriture annulée ne peut plus être corrigée ; une correction conserve la ligne remplacée.
13. Un paiement est idempotent par `submission_key` (double clic, rejeu réseau).
14. Le statut d'un compte est vérifié à chaque requête, pas seulement à la connexion.
15. Le dernier `SUPER_ADMIN` actif ne peut pas perdre son rôle.
16. Un rôle dissous (`COMPTABLE`, `ACCUEIL`) n'est plus attribuable ; ses lignes historiques restent lisibles.

---

## 9. Modèle de données

**37 modèles**, clé primaire `UUID` partout sauf `PlatformSetting` (`BigAutoField`, ligne unique `id = 1`). Tables nommées en `snake_case` pluriel quand c'est naturel. Champs en anglais, libellés en français.

### 9.1 Comptes et droits

| Table | Champs clés | Contraintes |
|---|---|---|
| `User` | `id`, `email`, `internal_code`, `account_status`, `phone`, `address`, `birth_date`, `disabled_at`, `display_name`, `avatar`, `roles` | E-mail unique, code interne unique, `USERNAME_FIELD = email`. |
| `Role` | `key`, `label`, `description`, `is_privileged` | Clé unique. |
| `Permission` | `key`, `description` | Clé unique. |
| `UserRole` | `user`, `role`, `assigned_by`, `assigned_at` | Unique `(user, role)`. |
| `RolePermission` | `role`, `permission` | Unique `(role, permission)`. |
| `AccessRequest` | `user`, `requested_role`, `assigned_role`, `status`, `reviewed_by`, `reviewed_at`, `decision_note` | Une demande ouverte par utilisateur. |
| `Notification` | `user`, `email`, `title`, `message`, `notification_type`, `is_read`, `sent_at` | Types compte, bourse, paiement, général. |
| `AuditLog` | `actor`, `action`, `entity_type`, `entity_id`, `before_summary`, `after_summary`, `ip_address`, `created_at` | Index `(entity_type, entity_id)` et `created_at`. |

### 9.2 Réglages

| Table | Champs clés | Contraintes |
|---|---|---|
| `AcademicYear` | `label`, `start_date`, `end_date`, `is_current` | Libellé unique, fin > début, une seule année en cours (index partiel). |
| `PlatformSetting` | `nom`, `signature`, `adresse`, `telephone`, `email`, `rccm`, `niu`, `cnss`, `devise`, `seuil_alerte`, `mise_a_jour_le` | Une seule ligne, seuil 1–100. |

### 9.3 Scolarité

| Table | Champs clés | Contraintes |
|---|---|---|
| `Course` | `title`, `domain`, `description`, `duration_months`, `fee_amount`, `monthly_fee_amount`, `currency`, `certificate_eligible`, `active` | Montants ≥ 0. |
| `CourseSession` | `name`, `course`, `starts_at`, `ends_at`, `schedule`, `capacity`, `status`, `formateurs` | Fin > début. |
| `Enrollment` | `student`, `session`, `status`, `enrolled_at`, `completed_at`, `start_date`, `ended_at`, `monthly_tariff_amount`, `tariff_amount`, `discount_amount`, `net_amount`, `payment_plan`, `registered_by`, `notes` | Unique `(student, session)`. |
| `Attendance` | `enrollment`, `session_record`, `date`, `status`, `arrival_time`, `absence_reason`, `recorded_by`, `note` | Unique `(enrollment, date)`. |
| `StudentSessionNote` | `enrollment`, `session_record`, `notions_learned`, `difficulties`, `observations`, `attended`, `followed_start`, `followed_end` | Unique `(enrollment, session_record)`. |
| `Certificate` | `enrollment`, `certificate_number`, `issued_at`, `issued_by`, `status` | Unique par inscription, numéro unique. |

### 9.4 Pédagogie

| Table | Champs clés | Contraintes |
|---|---|---|
| `Module` | `course`, `title`, `description`, `order`, `planned_hours` | Unique `(course, title)`. |
| `Lesson` | `module`, `title`, `objectives`, `order`, `planned_hours` | Unique `(module, title)`. |
| `SessionRecord` | `session`, `module`, `lesson`, `date`, `planned_start`, `planned_end`, `actual_start`, `actual_end`, `topic`, `objectives`, `content_covered`, `content_remaining`, `next_content`, `exercises_done`, `difficulties`, `notes`, `attendee_count`, `status`, `recorded_by` | Unique `(session, date, planned_start)`. |
| `Resource` | `title`, `description`, `course`, `module`, `lesson`, `session`, `kind`, `file`, `html_content`, `published_at`, `due_date`, `status`, `author` | Fichier ou HTML obligatoire, fichier ≤ 10 Mo. |
| `ResourceFeedback` | `resource`, `student`, `rating`, `comment` | Unique `(resource, student)`, note 1–5. |
| `StudentDocument` | `student`, `enrollment`, `doc_type`, `file`, `original_name`, `mime_type`, `size_bytes`, `uploaded_by` | Types identité, diplôme, relevé, photo, certificat, autre. |

### 9.5 Finance

| Table | Champs clés | Contraintes |
|---|---|---|
| `Payment` | `enrollment`, `amount`, `currency`, `method`, `submission_key`, `reference`, `status`, `motif`, `period_year`, `period_month`, `paid_at`, `recorded_by`, `transaction` | Référence unique, montant ≥ 1, `submission_key` unique. |
| `Expense` | `category`, `amount`, `currency`, `occurred_at`, `description`, `receipt`, `created_by`, `status`, `transaction` | Modèle hérité, n'alimente plus les indicateurs. |
| `CashAccount` | `name`, `kind`, `currency`, `opening_balance`, `active`, `overdraft_limit`, `archived_at`, `replaced_by` | Nom unique ; caisse, Mobile Money, banque. |
| `TransactionCategory` | `name`, `direction`, `active` | Unique `(name, direction)`. |
| `CashTransaction` | `reference`, `tx_type`, `category`, `label`, `description`, `amount`, `currency`, `occurred_at`, `account`, `destination_account`, `method`, `counterparty`, `receipt`, `status`, `nature`, `replaces`, `note`, `created_by` | Référence unique, montant ≥ 1, plancher de solde. |
| `CashClosure` | `account`, `date`, `opening_balance`, `theoretical_balance`, `counted_amount`, `difference`, `note`, `closed_by` | Unique `(account, date)`. |

### 9.6 Accueil, bourses, contrôle d'accès

| Table | Champs clés | Contraintes |
|---|---|---|
| `VisitReason` | `label`, `active`, `order` | Libellé unique. |
| `Contact` | `first_name`, `last_name`, `phone`, `secondary_phone`, `email`, `city`, `notes` | Réutilisable. |
| `Visit` | `reference`, `contact`, `visitor_type`, `reason`, `request_description`, `host_service`, `host_person`, `arrival_at`, `departure_at`, `agent`, `status`, `notes` | Référence `VIS-`. |
| `Prospect` | `reference`, `contact`, `course`, `domain`, `level`, `language_program`, `desired_start`, `preferred_contact`, `source`, `first_contact_at`, `agent`, `status`, `next_follow_up`, `converted_student`, `converted_at`, `visit` | Référence `PRO-`. |
| `ProspectFollowUp` | `prospect`, `occurred_at`, `contact_type`, `phone_used`, `summary`, `info_given`, `course`, `outcome`, `next_action`, `next_follow_up`, `agent` | — |
| `Destination` | `name`, `active` | Nom unique. |
| `ScholarshipApplication` | `reference`, `applicant_user`, `last_name`, `first_name`, `email`, `phone`, `destination`, `program`, `study_domain`, `status`, `reviewed_by`, `review_note`, `tracking_token` | Référence `BRS-`, jeton unique. |
| `ScholarshipDocument` | `application`, `document_type`, `file`, `original_name`, `mime_type`, `size_bytes` | Types identité, diplôme, relevé, photo, motivation. |
| `AccessEvent` | `person`, `visitor_label`, `event_type`, `occurred_at`, `recorded_by`, `reason` | Entrée ou sortie. |

### 9.7 Règles de modélisation

- Clés étrangères en `UUID` sauf `PlatformSetting`.
- `on_delete=PROTECT` pour tout ce qui a une valeur historique ; `CASCADE` réservé aux dépendances pures.
- Propriétés calculées (`net_amount`, `reste à payer`, `solde`, `taux de présence`) dans le modèle ou le service, pas dans le template.
- Contraintes `UniqueConstraint` et `CheckConstraint` déclarées dans `Meta.constraints`.
- Méthodes de génération de références centralisées (`PREFIX-ANNEE-0001`).
- Aucune donnée métier dans les migrations de données sauf jeu de référence explicitement documenté.

---

## 10. Routes et navigation

Routes nommées, préfixées par le domaine. Principales familles :

| Domaine | Préfixe | Exemples |
|---|---|---|
| Public | `/` | ``, `login/`, `register/`, `demande-acces/`, `pending-approval/`, `access-denied/` |
| Bourses | `/bourses/` | `candidature/`, `confirmation/<reference>/`, `suivi/` |
| Dashboard | `/dashboard/` | `profil/`, `notifications/poll/`, routeur par rôle |
| Supervision | `/dashboard/super-admin/` | `users/`, `permissions/`, `access-requests/`, `audit/`, `finances/`, `scholarships/` |
| Secrétariat | `/dashboard/secretaire/` | `etudiants/`, `inscriptions/nouvelle/`, `<id>/valider/` |
| Accueil | `/dashboard/accueil/` | `visites/`, `prospects/`, `motifs/`, `contacts/recherche/` |
| Pédagogie | `/dashboard/pedagogie/` | `programmes/`, `formations/`, `modules/`, `lecons/`, `groupes/`, `seances/`, `presences/`, `cahier-de-texte/`, `ressources/`, `progression/` |
| Comptabilité | `/dashboard/comptabilite/` | `journal/`, `operations/`, `caisses/`, `categories/`, `clotures/`, `paiement/`, `recu/<id>/` |
| Réglages | `/dashboard/reglages/` | `parametres-generaux/`, `annees-academiques/` |
| Fichiers | `/` | `documents/<uuid>/`, `media/avatars/<path>` |

Navigation attendue :

- Menu latéral filtré par rôle et par permissions ; jamais de lien vers un écran qui renverra 403.
- Fil d'Ariane sur les écrans de détail.
- Actions destructives présentées comme « annuler », « archiver », « désactiver ».
- Retour sur l'ancre ou la liste après création, avec message de succès.

---

## 11. Synchronisation Google Sheets

### 11.1 Sources

Deux classeurs privés, identifiants par défaut :

```text
1skjUY883GPpTOlG9nYP_Z6PrAj60rQ47NvTfpRYygCU
1GmjRV7T1dcLCD9kQd_hphdYLrO1Z6ezfgwd9xIA41gU
```

Remplaçables par `CLASSEURS_GOOGLE_IDS` ou `--feuille id1 --feuille id2`.

### 11.2 Authentification

**Compte de service obligatoire** pour des données d'élèves et de caisse. Pas de partage public.

1. Projet Google Cloud, APIs **Drive** et **Sheets** activées.
2. Compte de service, clé JSON déposée hors dépôt :
   `C:\Users\<vous>\.config\academy\service-account.json`.
3. Chaque feuille partagée avec le `client_email` du JSON, rôle **Lecteur**.
4. Aucune réécriture dans Google.

Le mode public reste possible pour des classeurs de démonstration, jamais pour les données réelles.

### 11.3 Chaîne de synchronisation

| Commande | Rôle |
|---|---|
| `manage.py migrer` | Sauvegarde seulement si une migration attend, puis applique. |
| `manage.py etat_google` | Affiche le `client_email` et vérifie chaque feuille, sans télécharger. |
| `manage.py synchroniser_classeurs` | Télécharge, classe, analyse, écrit le rapport. **N'écrit rien en base.** |
| `manage.py synchroniser_classeurs --ecrire` | Sauvegarde, importe, retire la sauvegarde si rien n'a changé. |
| `.\synchroniser.ps1` | `migrer` puis synchronisation en écriture, journalisée. |
| `.\installer_tache_synchronisation.ps1` | Installe ou retire la tâche Windows horaire. |

### 11.4 Classement et imports

- Classeur `Base Etudiants` → `importer_etudiants`.
- Onglet `Enregistrement_Opérations` ou `Feuille 2` → `importer_feuille`.
- Tout le reste → `inconnu`, signalé, jamais importé.
- Un conflit avec une saisie applicative arrête l'import : `importer_etudiants` refuse d'écraser sans `--efface`.
- Les fichiers reçus vont dans `docs/donnees/import_<date>/`, le rapport dans `RAPPORT_ANALYSE.md`.
- Les imports précédents sont archivés dans `archive/<horodatage>/`.

### 11.5 Fréquence et exploitation

- Relecture **toutes les heures** : Google Sheets n'a pas de notification vers l'application.
- La base reste la source de service ; une panne Google ne bloque pas le guichet.
- Tâche Windows **UniversAcademy - Synchronisation** : démarrage horaire, session interactive de l'utilisateur, `IgnoreNew`, limite 50 minutes, `-ExecutionPolicy Bypass`.
- Journal `synchronisation.log`, rotation à 5 Mo vers `synchronisation.log.1`.
- Sans JSON : journal « Compte de service absent », sortie propre, pas d'échec.
- Échec réel : code de sortie non nul et détail dans le journal.
- Première installation en **aperçu** (`-SansEcrire`) ; passage en écriture après lecture du rapport.

### 11.6 Sauvegarde avant écriture

- `sauvegarder_base()` copie `db.sqlite3` dans `backups/db_AAAAmmjj_HHMMSS_auto.sqlite3`.
- La copie est posée **avant** les importeurs.
- `empreinte_base()` (date de modification + taille) permet de retirer la copie si la base n'a pas changé.
- La copie reste si une écriture a eu lieu ou si un importeur a échoué.
- Sur PostgreSQL, la sauvegarde relève de `pg_dump` et de l'exploitation.

### 11.7 Critères d'acceptation

- `etat_google` liste le `client_email` et l'état de chaque feuille sans téléchargement.
- Un aperçu ne modifie ni la base ni `backups/`.
- Une écriture réelle pose une copie, conservée seulement si la base change.
- Une exécution sans changement ne laisse pas de copie supplémentaire.
- Un classeur inconnu est signalé et ignoré.
- Un conflit laisse une trace et un code de sortie non nul.
- La tâche est visible dans `taskschd.msc` avec un dernier résultat consultable.

---

## 12. Sauvegardes et migrations

| Déclencheur | Comportement |
|---|---|
| Migration en attente (`migrer`) | Copie avant `migrate`, puis application. |
| Aucune migration en attente | Aucune copie, aucune écriture. |
| Synchronisation en écriture | Copie avant importeurs, retirée si la base n'a pas changé. |
| Maintenance manuelle | Copie préalable recommandée. |
| PostgreSQL | `pg_dump` / restauration par l'exploitation. |

`manage.py migrer --verifier` ajoute `check` et `makemigrations --check --dry-run` : la commande échoue si du code attend une migration non générée. C'est le contrôle de déploiement.

`demarrer.ps1` et `synchroniser.ps1` appellent `migrer` : le serveur ne démarre jamais sur un schéma en retard.

---

## 13. Interface et expérience utilisateur

- **Français** par défaut, anglais disponible ; libellés traduits, aucun texte en dur dans les templates.
- Tailwind compilé ; thème clair/sombre persistant, sélecteur de langue dans l'en-tête.
- Formulaires accessibles : `label` associé, messages d'erreur au champ, focus visible.
- Formulaires en ligne natifs (`<details>`) pour les créations rapides ; pas de dépendance JavaScript pour les parcours critiques.
- Tableaux lisibles, pagination, filtres conservés dans l'URL, états vides explicites.
- Imprimés propres : reçu de paiement, cahier de texte, feuille de suivi, attestation.
- Couleurs et typographie sobres, adaptées à un usage administratif quotidien.
- Aucune action proposée si l'utilisateur n'a pas le droit : masquage **et** contrôle serveur.
- Les montants affichés utilisent la devise des réglages, avec séparateurs de milliers.

---

## 14. Exigences non fonctionnelles

| ID | Exigence | Cible |
|---|---|---|
| NFR-01 | Listes courantes | < 500 ms sur la base de référence |
| NFR-02 | Tableaux de bord | < 2 s |
| NFR-03 | Capacité | Plusieurs centaines d'étudiants, milliers d'écritures sur SQLite ; PostgreSQL au-delà |
| NFR-04 | Disponibilité | Heures ouvrées ; la base reste servie si Google est indisponible |
| NFR-05 | Sauvegarde | Copie avant toute écriture automatisée ; RPO ≤ 1 h pour la synchronisation |
| NFR-06 | Restauration | Procédure documentée et testée |
| NFR-07 | Traçabilité | Toute action sensible auditée |
| NFR-08 | Internationalisation | Français par défaut, anglais disponible, aucun mélange |
| NFR-09 | Accessibilité | Navigation clavier, libellés, contrastes |
| NFR-10 | Compatibilité | Chrome, Edge, Firefox récents |
| NFR-11 | Maintenabilité | Code découpé par domaine, services dédiés, tests |
| NFR-12 | Observabilité | Journal de synchronisation, audit métier, sorties de commandes |
| NFR-13 | Portabilité | SQLite local ou PostgreSQL par variable d'environnement |
| NFR-14 | Dépendances | Versions minimales déclarées, veille sur les vulnérabilités |

---

## 15. Sécurité et confidentialité

- Mots de passe hachés par Django ; validateurs : similarité, longueur minimale 8, mot de passe courant, entièrement numérique.
- Sessions serveur ; cookie `HttpOnly`.
- En production (`DEBUG=False`) : cookies sécurisés, redirection SSL, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, HSTS.
- Documents privés sous `media/private/`, servis uniquement par une vue authentifiée ; avatars par une vue dédiée.
- Taille des fichiers : avatars 2 Mo, ressources 10 Mo ; extensions contrôlées pour les pièces.
- Aucun secret dans le dépôt ; `.gitignore` bloque les JSON de compte de service.
- Journal d'audit : acteur, action, entité, résumé avant/après, IP, horodatage.
- Avant exposition publique : `DEBUG=False`, `SECRET_KEY` long et unique, HSTS, comptes de démonstration désactivés, limitation de débit sur la connexion.

---

## 16. Commandes d'exploitation

À fournir, documenter et tester :

```text
migrer                         Applique les migrations ; sauvegarde si attente
etat_google                    Diagnostic compte de service et accès aux feuilles
synchroniser_classeurs         Télécharge, analyse, importe sur --ecrire
analyser_donnees               Rapport d'analyse d'un dossier de classeurs
importer_formations            Catalogue des formations
importer_etudiants             Élèves, groupes, inscriptions, paiements
importer_feuille               Rapproche et importe le journal de caisse
mettre_en_attente              Place des comptes en attente selon les classeurs
regulariser_dates_caisse       Corrige les dates de caisse futures, avec audit
verifier_relations             16 contrôles de cohérence, lecture seule
audit_finances                 Contrôles financiers, lecture seule
audit_privileges               Contrôles des attributions de rôles
verifier_i18n                  Messages non traduits
compiler_traductions           Compile les fichiers de traduction
seed_roles                     Crée les rôles de référence
seed_demo                      Jeu de démonstration, mots de passe générés
purger_donnees_fictives        Purge encadrée des données de démonstration
create_superadmin              Crée un super administrateur initial
```

Chaque commande destructrice ou d'import accepte un mode aperçu et affiche un résumé avant/après. Les commandes de contrôle sortent en erreur si un écart est détecté (`--maxi 0` pour un portique).

---

## 17. Tests et recette

### 17.1 Niveaux

| Niveau | Moyen | Périmètre |
|---|---|---|
| Automatisé | `python manage.py test core.tests` | Modèles, formulaires, vues, permissions, imports, synchronisation, sauvegardes |
| Système | `python manage.py check` | Configuration Django |
| Migrations | `python manage.py migrer --verifier` | `check` + `makemigrations --check --dry-run` |
| Relations | `python manage.py verifier_relations` | 16 contrôles, lecture seule |
| Finances | `python manage.py audit_finances` | Trop-perçus, paiements sans caisse, écarts, soldes négatifs, dates futures |
| Privilèges | `python manage.py audit_privileges` | Attributions de rôles à vérifier |
| i18n | `python manage.py verifier_i18n --maxi 0` | Messages balisés et traduits |
| Recette | Navigateur | Parcours par rôle, impressions, refus 403 |

### 17.2 Cible de référence

- **684 tests** verts (dernière exécution connue au 10/11/2026), sur la base de test Django.
- `manage.py check` : aucun problème.
- La base de production n'est jamais touchée par les tests.

### 17.3 Scénarios d'acceptation obligatoires

| Scénario | Résultat attendu |
|---|---|
| Inscription publique comme formateur | Compte en attente, demande enregistrée, aucun rôle. |
| Approbation par le super administrateur | Rôle attribué, code interne généré, notification, audit, accès autorisé. |
| `ADMIN` tente de modifier un rôle | 403, aucun changement, aucun audit trompeur. |
| `RESP_PEDA` crée un module | Module visible, ordre suivant, audit `MODULE_CREATE`, retour sur l'ancre. |
| `ADMIN` tente de créer un module | 403, formulaire absent. |
| Remise supérieure au tarif | Refus explicite, aucune écriture. |
| Direction valide une inscription | Compte étudiant actif, groupe rattaché, audit `ENROLLMENT_VALIDATE`. |
| Encaissement supérieur au reste à payer | Refus. |
| Sortie au-delà du découvert | Refus avec montant manquant, y compris par script. |
| Transfert vers la même caisse | Refus. |
| Double présence le même jour | Seconde saisie ignorée, ligne d'origine conservée. |
| Étudiant lit une ressource brouillon | 404/403, aucune fuite. |
| Document privé téléchargé sans droit | 404, aucune fuite. |
| Tâche horaire sans JSON | Sortie propre, journal « Compte de service absent ». |
| Synchronisation en aperçu | Base et `backups/` inchangés. |
| Synchronisation en écriture sans changement | Aucune copie conservée. |

---

## 18. Méthode de travail imposée

### Phase 0 — Restitution de conception (aucun code)

Produire et faire valider :

1. l'arborescence cible et les modules ;
2. la liste des 37 modèles avec leurs relations et contraintes ;
3. la carte des routes et des écrans par rôle ;
4. la matrice des accès et la liste des 19 permissions ;
5. les règles de gestion critiques (section 8) ;
6. les risques techniques et les choix à confirmer ;
7. le plan de livraison par jalons.

**Aucune ligne de code avant validation de cette restitution.**

### Phase 1 — Socle

- Projet Django, settings, `.env.example`, base SQLite.
- `User`, `Role`, `Permission`, `UserRole`, `RolePermission`, `AccessRequest`, `AuditLog`, `Notification`.
- Authentification locale, middleware de statut, décorateurs.
- Portail public, inscription, demande d'accès, connexion, tableaux de bord minimaux.
- Tests : comptes, statuts, rôles, permissions, refus 403.

**Point de contrôle** : `check` propre, tests du socle verts, parcours d'inscription complet.

### Phase 2 — Métier

- Accueil, visites, prospects, contacts.
- Étudiants, inscriptions, documents, certificats.
- Réglages, années académiques.
- Audit branché sur les créations et modifications.
- Tests : scolarité, accueil, réglages, année.

**Point de contrôle** : un étudiant peut être créé, inscrit, validé, documenté ; les refus métier sont testés.

### Phase 3 — Pédagogie

- Catalogue, modules, leçons, formulaires en ligne, ancres.
- Groupes, séances, présences, cahier de texte, progression.
- Ressources, retours, espace étudiant.
- Tests : pédagogie, périmètre formateur, impressions.

**Point de contrôle** : scénario complet formation → module → leçon → groupe → séance → présence → fiche → ressource.

### Phase 4 — Finance

- Caisses, catégories, journal, opérations, transferts, clôtures.
- Paiements, reçus, supervision.
- Services `caisse.py`, contrôles `relations.py` et `audit_finances`.
- Tests : comptabilité, soldes, découvert, idempotence, dates futures.

**Point de contrôle** : soldes justes, aucun dépassement possible, reçus imprimables.

### Phase 5 — Google et exploitation

- `google_sheets.py`, `etat_google`, `synchroniser_classeurs`, imports.
- `sauvegarde.py`, `migrer`, scripts PowerShell, tâche horaire.
- Rapport d'analyse, documentation d'exploitation.
- Tests : synchronisation, sauvegarde conditionnelle, absence de JSON.

**Point de contrôle** : aperçu sans écriture, écriture avec sauvegarde, tâche installée en aperçu.

### Phase 6 — Recette et livraison

- Suite complète, `check`, `migrer --verifier`, `verifier_relations`, `audit_finances`, `verifier_i18n`.
- Recette manuelle par rôle, impressions, refus.
- Documentation : cahier des charges, mode d'emploi, hébergement, synchronisation.
- Nettoyage : code mort, imports inutiles, fichiers temporaires.

### Règles de travail

- Une unité de travail = un objectif testable, un diff lisible, un compte rendu court.
- Ne jamais modifier la base de production pendant le développement ; utiliser la base de test ou une copie.
- Ne jamais ajouter une dépendance sans la déclarer et justifier.
- Ne jamais modifier un test pour le faire passer sans corriger le comportement, sauf test erroné documenté.
- Signaler toute ambiguïté avant de coder ; proposer une option par défaut.
- Vérifier la parité français/anglais après toute chaîne ajoutée.
- Respecter les conventions existantes : noms de routes, services, partiels, messages.

---

## 19. Livrables et jalons

| Jalon | Contenu | Condition de passage |
|---|---|---|
| J1 — Socle | Authentification, rôles, étudiants, inscriptions, caisse initiale. | Tests verts, recette des rôles. |
| J2 — Pédagogie | Catalogue, modules/leçons, groupes, séances, présences, ressources. | Recette avec le responsable pédagogique. |
| J3 — Finance | Paiements, reçus, clôtures, supervision, contrôles. | Soldes justes, audits verts sur base de test. |
| J4 — Google | JSON, partage, aperçu, écriture, tâche horaire. | `etat_google` complet, rapport d'analyse validé. |
| J5 — Production | Sécurité, sauvegardes, restauration, documentation, formation. | Recette finale signée. |

Livrables documentaires :

| Document | Usage |
|---|---|
| `docs/CAHIER_DES_CHARGES.md` et `.docx` | Spécification de référence. |
| `docs/SYNCHRONISATION_GOOGLE.md` | Accès Google, tâche horaire, sauvegardes. |
| `VALIDATION_METIER.md` | Règles métier, couverture des tests, points ouverts. |
| `RAPPORT_TESTS_<date>.md` | Résultat de la campagne de tests. |
| `docs/Mode_emploi_Univers_Academy.docx` | Mode d'emploi utilisateur. |
| `docs/Hebergement_Univers_Academy.docx` | Contraintes d'hébergement. |
| `README` ou guide de démarrage | Installation, commandes, comptes initiaux. |

---

## 20. Définition de « terminé »

Une fonctionnalité est terminée quand **tout** est vrai :

- [ ] Le comportement est implémenté côté serveur, pas seulement affiché.
- [ ] Les droits sont appliqués par décorateur ou filtre de requête.
- [ ] Les cas d'erreur ont un message clair, en français.
- [ ] L'action sensible écrit une ligne d'audit.
- [ ] Les textes sont traduits en français et en anglais.
- [ ] Un test automatisé couvre le cas nominal et au moins un refus.
- [ ] `manage.py check` est propre.
- [ ] La suite `manage.py test core.tests` passe intégralement.
- [ ] Aucune migration manquante (`migrer --verifier`).
- [ ] L'écran est utilisable au clavier et lisible sur un écran courant.
- [ ] La documentation d'exploitation est à jour si l'exploitation change.
- [ ] Aucun secret, aucune donnée réelle, aucun fichier temporaire n'entre dans le dépôt.

---

## 21. Interdits (anti-patrons à refuser)

1. Autoriser une action parce que le bouton est caché.
2. Faire confiance à un identifiant envoyé par le formulaire sans vérifier son périmètre.
3. Écrire un montant, une devise ou un libellé d'établissement en dur.
4. Supprimer une ligne référencée par l'historique.
5. Recalculer un solde à partir des seuls paiements ou des seules écritures de caisse.
6. Encaisser sans clé d'idempotence.
7. Laisser une écriture validée dans le futur.
8. Lancer une migration sans sauvegarde quand elle est en attente.
9. Remplir `backups/` à chaque passage horaire.
10. Télécharger les feuilles Google à chaque requête utilisateur.
11. Partager publiquement un classeur contenant des données d'élèves.
12. Stocker le JSON de compte de service dans le dépôt.
13. Modifier un test pour masquer une régression.
14. Ajouter une dépendance non déclarée.
15. Livrer un écran sans contrôle serveur ni test de refus.

---

## 22. Prompt condensé (variante courte)

> Tu es développeur Django senior. Conçois et réalise **Univers Academy**, une plateforme de gestion de centre de formation à Brazzaville : portail public, bourses, accueil/visites/prospects, secrétariat (étudiants, inscriptions, documents), pédagogie (catalogue, modules, leçons, groupes, séances, présences, cahier de texte, ressources), comptabilité (caisse multi-comptes, clôtures, paiements, reçus), réglages, comptes/rôles/audit, et synchronisation horaire de deux Google Sheets privés via compte de service.
>
> Pile : Python 3, Django 5.2, SQLite ou PostgreSQL par `DATABASE_URL`, Tailwind compilé, `openpyxl`, `google-auth`, interface française traduisible, 37 modèles en UUID, 8 rôles actifs, 19 permissions fines.
>
> Règles non négociables : contrôle serveur de chaque action, aucune authentification externe, aucune suppression destructive (archiver/annuler/désactiver), sauvegarde avant toute écriture automatisée, migrations idempotentes (`migrer` ne sauvegarde que si une migration attend), jamais de réécriture dans Google, base = source de service, audit de toute action sensible, 684 tests verts et `check` propre avant livraison.
>
> Droits : `SUPER_ADMIN` et `ADMIN` lisent tout mais n'écrivent pas le métier courant ; exceptions caisse/paiements, groupes et modification d'inscription existante. Validation d'inscription : direction, assistant administratif, responsable pédagogique, super administrateur. Formateur limité à ses groupes. Actes réservés au super administrateur : comptes, rôles, statuts, permissions, décision de bourse.
>
> Livre par phases : socle, métier, pédagogie, finance, Google/exploitation, recette. Avant de coder, produis la restitution de conception (arborescence, modèles, routes, matrice des droits, règles critiques, plan). À chaque phase : `manage.py check`, `manage.py test core.tests`, compte rendu court. Documente l'exploitation et les sauvegardes. Refuse tout raccourci qui affaiblit la sécurité ou la traçabilité.

---

*Fin du prompt de conception — version 1.0 du 11 novembre 2026.*
