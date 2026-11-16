# Cahier des charges

## Univers Academy — plateforme de gestion d'un centre de formation

| Rubrique | Valeur |
|---|---|
| Version | 1.0 |
| Date de référence | 10 novembre 2026 |
| Statut | Version de référence, alignée sur le code et la base au 10/11/2026 |
| Destinataires | Direction, responsable pédagogique, secrétariat, comptabilité, administration, prestataire technique |
| Périmètre | Portail public, back-office métier, pédagogie, comptabilité, bourses, synchronisation Google Sheets |
| Langue de l'interface | Français (anglais disponible par le sélecteur de langue) |
| Dépôt | `D:\Dev\01_Professionnel\Django\academy` |

> **Légende des statuts** : **Réalisé** = présent dans le code et couvert par les tests ; **Partiel** = présent mais incomplet ou non exploité ; **À faire** = spécifié mais non implémenté.
>
> **Priorités MoSCoW** : **M** = indispensable, **S** = souhaitable, **C** = optionnel.

## Sommaire

0. Résumé exécutif
1. Contexte et présentation
2. Objectifs
3. Périmètre
4. Acteurs, rôles et droits
5. Exigences fonctionnelles
6. Règles de gestion
7. Parcours et scénarios
8. Modèle de données
9. Architecture et choix techniques
10. Intégration Google Sheets
11. Sécurité, confidentialité et sauvegardes
12. Exigences non fonctionnelles
13. Contraintes et hypothèses
14. Recette et critères d'acceptation
15. Exploitation et déploiement
16. Risques et points ouverts
17. Livrables et jalons
- Annexes A à F (glossaire, routes, commandes, variables, traçabilité, références)

---

## 0. Résumé exécutif

Univers Academy est une application web de gestion d'un centre de formation. Elle réunit dans une seule base les dossiers étudiants, les inscriptions, le catalogue pédagogique, les groupes, les séances, les présences, les ressources, la caisse, les paiements, les bourses et le journal d'audit. Elle remplace la dispersion entre classeurs Excel/Google Sheets, fichiers locaux et saisies parallèles.

Le système est aujourd'hui fonctionnel sur son cœur métier : authentification locale, dix rôles, dossiers étudiants, inscriptions et encaissements, pédagogie, comptabilité de caisse, supervision, réglages d'établissement, journal d'audit et 684 tests automatisés. Une synchronisation horaire des deux classeurs Google est spécifiée et outillée ; son activation en écriture reste conditionnée à la fourniture du fichier de compte de service Google et au partage des deux feuilles avec son adresse `client_email`.

Le présent document constitue le cahier des charges de référence : il décrit le besoin, le périmètre, les acteurs, les exigences fonctionnelles et non fonctionnelles, les règles de gestion, l'architecture, les intégrations, la sécurité, la recette et les conditions d'exploitation.

---

## 1. Contexte et présentation

### 1.1 L'établissement

Univers Academy est un centre de formation implanté à Brazzaville (République du Congo). Il propose des formations organisées par domaine, en groupes, avec un suivi de présence, un cahier de texte, des supports pédagogiques et une facturation mensuelle ou forfaitaire.

L'établissement dispose d'une identité administrative propre (nom, signature, adresse, téléphone, e-mail, RCCM, NIU, CNSS) et d'une devise d'affichage paramétrable. Ces éléments alimentent les écrans, les reçus et les documents imprimés.

### 1.2 Situation initiale et problème à résoudre

Avant l'application, les informations vivaient dans plusieurs fichiers :

- un classeur des élèves pour les comptes, groupes, inscriptions et paiements ;
- un classeur « journal de caisse » pour les encaissements et dépenses ;
- des documents administratifs et pédagogiques séparés ;
- des tableaux de suivi tenus à la main.

Cette organisation produisait des doublons, des montants divergents entre le dossier étudiant et la caisse, des oublis de mise à jour, une traçabilité faible et une dépendance à la disponibilité d'un fichier ou d'une personne.

### 1.3 Objet du document

Ce cahier des charges vise à :

1. décrire le besoin métier et les règles que l'application doit respecter ;
2. fixer le périmètre de la version de référence et ce qui en est exclu ;
3. préciser les acteurs, leurs droits et les parcours attendus ;
4. définir les exigences fonctionnelles, les règles de gestion et les critères d'acceptation ;
5. décrire l'architecture, les intégrations et les contraintes d'exploitation ;
6. servir de base à la recette, à la maintenance et aux évolutions.

### 1.4 Terminologie

| Terme | Définition |
|---|---|
| **Formation** (`Course`) | Catalogue : intitulé, domaine, durée, frais, tarif mensuel de référence, éligibilité au certificat. |
| **Module** (`Module`) | Sous-partie d'une formation, ordonnée, avec une durée prévue. |
| **Leçon** (`Lesson`) | Sous-partie d'un module, avec des objectifs et une durée prévue. |
| **Groupe** (`CourseSession`) | Occurrence datée d'une formation, avec horaires, capacité, statut et formateurs. |
| **Inscription** (`Enrollment`) | Dossier liant un étudiant à un groupe, avec tarif, remise, net dû et statut. |
| **Séance** (`SessionRecord`) | Séance planifiée puis réalisée, rattachée à un groupe, éventuellement à un module et une leçon. |
| **Présence** (`Attendance`) | Statut d'un étudiant inscrit à une date donnée. |
| **Caisse** (`CashAccount`) | Compte d'espèces, Mobile Money ou bancaire, avec solde d'ouverture et découvert autorisé. |
| **Écriture** (`CashTransaction`) | Entrée, sortie ou transfert validé, brouillon ou annulé. |
| **Paiement étudiant** (`Payment`) | Règlement rattaché à une inscription, relié à une écriture de caisse. |
| **Rôle** | Poste de travail déterminant les écrans et les actions autorisées. |
| **Compte de service** | Robot Google (`...@....iam.gserviceaccount.com`) utilisé pour lire les feuilles privées. |

---

## 2. Objectifs

### 2.1 Objectif général

Doter l'établissement d'une source unique, fiable, traçable et sécurisée pour la gestion administrative, pédagogique et financière, tout en conservant les classeurs Google comme source d'alimentation périodique.

### 2.2 Objectifs spécifiques

| Objectif | Indicateur attendu |
|---|---|
| Centraliser les dossiers étudiants | Un dossier par étudiant, consultable avec ses inscriptions, paiements, documents et présences. |
| Sécuriser les accès | Chaque action est contrôlée côté serveur ; aucun rôle ne voit ni ne modifie au-delà de son périmètre. |
| Fiabiliser la caisse | Toute recette ou dépense passe par une écriture ; le solde ne descend jamais sous le plancher autorisé. |
| Rendre la pédagogie exploitable | Catalogue, modules, leçons, groupes, séances, présences, cahier de texte et ressources consultables par les bons acteurs. |
| Tracer les actes sensibles | Journal d'audit horodaté avec auteur, action, entité, valeurs avant/après et adresse IP. |
| Réduire la double saisie | Synchronisation horaire des classeurs Google vers la base, avec rapport d'analyse et sauvegarde préalable. |
| Donner de la visibilité | Tableaux de bord par rôle avec compteurs, indicateurs financiers et files de travail. |
| Permettre l'exploitation locale | Fonctionnement sur un poste Windows avec SQLite, sans dépendance à un serveur externe pour le cœur métier. |

### 2.3 Résultats attendus

- Le secrétariat crée un étudiant, un dossier d'inscription et un encaissement sans recourir à un tableur.
- Le responsable pédagogique crée une formation, ses modules et ses leçons directement depuis l'écran « Programmes ».
- Le formateur saisit ses séances, ses présences et son cahier de texte ; l'étudiant consulte ses ressources, ses présences et sa fiche de cours.
- La comptabilité tient une caisse unique, avec des soldes justes, des reçus et des clôtures.
- La direction consulte les indicateurs consolidés et arbitre les écarts signalés.
- Les classeurs Google sont relus chaque heure ; la base reste la source de service, même si Google est indisponible.

---

## 3. Périmètre

### 3.1 Dans le périmètre

- Portail public : accueil, présentation de l'établissement, candidature et suivi de bourse.
- Authentification locale, inscription, demandes d'accès, approbation et gestion des comptes.
- Dix rôles et une matrice de permissions fine.
- Accueil : visites, motifs, contacts, prospects, relances et conversion en étudiant.
- Secrétariat : dossiers étudiants, inscriptions, documents, photos.
- Pédagogie : catalogue, modules, leçons, groupes, séances, présences, cahier de texte, progression, ressources, fiches de cours.
- Comptabilité : caisses, catégories, journal, transferts, clôtures, paiements étudiants, reçus, supervision.
- Bourses : candidature publique, pièces, instruction, décision.
- Réglages : identité de l'établissement, devise, seuil d'alerte, années académiques.
- Journal d'audit, notifications, profil utilisateur.
- Synchronisation Google Sheets : téléchargement, classement, analyse, import, sauvegarde.
- Administration Django en consultation pour les tables sensibles.

### 3.2 Hors périmètre de la version de référence

| Élément exclu | Précision |
|---|---|
| Paiement en ligne | Aucun prestataire de paiement n'est intégré ; les encaissements sont saisis au guichet. |
| Application mobile native | L'interface est web responsive ; pas de client iOS/Android dédié. |
| Visioconférence / classe virtuelle | Les ressources et le cahier de texte sont gérés, pas les salles virtuelles. |
| Gestion de la paie | Les salaires sont suivis par catégorie comptable, sans modèle de paie ni de masse salariale. |
| Remboursement complet d'un paiement | L'annulation se fait au niveau de l'écriture de caisse ; le statut du paiement lié n'est pas mis à jour automatiquement. |
| Exports PDF natifs | Seuls les exports CSV du journal et de la supervision existent ; les reçus et documents sont imprimés depuis le navigateur. |
| Statistiques analytiques avancées | Les totaux de base existent ; pas de rapports multidimensionnels ni de prévisions. |
| Notifications métier par e-mail | Seules les notifications d'approbation et de refus de compte sont créées ; aucun envoi réel n'est déclenché. |
| Tests end-to-end navigateur | Les tests sont des tests Django (vues, formulaires, modèles, permissions), sans Selenium/Playwright. |
| Haute disponibilité multi-serveurs | La cible est un poste ou un serveur unique ; pas de réplication ni de bascule automatique. |

---

## 4. Acteurs, rôles et droits

### 4.1 Statuts de compte

| Statut | Effet |
|---|---|
| `PENDING_APPROVAL` | Le compte existe mais n'accède à aucun écran métier ; il est redirigé vers la complétion de sa demande d'accès. |
| `ACTIVE` | Accès autorisé selon les rôles. |
| `SUSPENDED` | Accès bloqué, y compris sur une session déjà ouverte. |
| `DISABLED` | Accès bloqué ; `disabled_at` est renseigné. |
| `REJECTED` | Demande refusée ; accès bloqué. |

Le statut est contrôlé à chaque requête par le middleware `AccountStatusMiddleware`, sauf pour les pages publiques, les fichiers statiques, l'administration Django et les documents privés servis par leur vue dédiée.

### 4.2 Rôles

| Rôle | Mission principale | Tableau de bord | Préfixe de code interne |
|---|---|---|---|
| `SUPER_ADMIN` | Administration technique, comptes, rôles, audit, supervision, caisse. | `/dashboard/super-admin/` | `UA-ADM` |
| `ADMIN` | Accès transversal en lecture, caisse, traitement des demandes d'accès, consultation des bourses. | `/dashboard/admin/` | `UA-ADM` |
| `DIRECTION` | Pilotage, validation des inscriptions, catalogue, réglages, années académiques. | `/dashboard/direction/` | `UA-DIR` |
| `ASSISTANT_ADMIN` | Assistance administrative et comptable (poste issu de la fusion des anciens postes). | `/dashboard/comptabilite/` | `UA-ASY` |
| `SECRETAIRE` | Dossiers étudiants, inscriptions au guichet, documents, consultation pédagogique. | `/dashboard/secretaire/` | `UA-SEC` |
| `RESP_PEDA` | Catalogue, modules, leçons, groupes, séances, ressources, validation pédagogique. | `/dashboard/responsable-pedagogique/` | `UA-RPD` |
| `FORMATEUR` | Groupes affectés, séances, présences, cahier de texte, ressources. | `/dashboard/formateur/` | `UA-FRM` |
| `ETUDIANT` | Ressources publiées, présences, fiches de cours, espace personnel. | `/dashboard/etudiant/` | `UA-ETU` |
| `COMPTABLE` | Ancien poste, conservé pour l'historique ; plus attribuable ni proposé dans les menus. | — (rôle historique) | `UA-CPT` |
| `ACCUEIL` | Ancien poste, conservé pour l'historique ; plus attribuable ni proposé dans les menus. | — (rôle historique) | `UA-ACC` |

**Rôles réellement attribuables** : `SUPER_ADMIN`, `ADMIN`, `DIRECTION`, `ASSISTANT_ADMIN`, `SECRETAIRE`, `RESP_PEDA`, `FORMATEUR`, `ETUDIANT`.

**Rôles qu'un demandeur peut solliciter** : `ETUDIANT`, `FORMATEUR`, `SECRETAIRE`, `ASSISTANT_ADMIN`, `RESP_PEDA`. Les rôles `SUPER_ADMIN`, `ADMIN` et `DIRECTION` ne passent jamais par le formulaire public.

### 4.3 Règles transversales d'autorisation

1. **Contrôle serveur** : les décorateurs `role_required`, `business_write_required`, `cash_write_required`, `payment_write_required`, `permission_required`, `super_admin_required` et `enrollment_validation_required` refusent par un HTTP 403, jamais par un simple masquage d'interface.
2. **Rôles transversaux** : `SUPER_ADMIN` et `ADMIN` accèdent en lecture à tous les modules. Ils ne peuvent pas écrire le métier courant (visites, prospects, étudiants, inscriptions à la création, présences, séances, ressources, modules, leçons).
3. **Exception caisse et paiements** : la caisse est ouverte en écriture aux rôles transversaux (opération, annulation, correction, paiement étudiant, clôture, compte, catégorie), avec trace d'audit. L'encaissement d'un paiement étudiant suit la matrice `finance.write`.
4. **Exception groupes** : la création et la modification d'un groupe sont ouvertes à `RESP_PEDA`, `DIRECTION`, `SUPER_ADMIN` et `ADMIN` par la route dédiée ; les autres écritures pédagogiques (séances, présences, ressources, modules, leçons) restent fermées aux rôles transversaux.
5. **Exception inscription existante** : la modification d'une inscription est ouverte à `SECRETAIRE`, `DIRECTION`, `SUPER_ADMIN` et `ADMIN`, avec audit `ENROLLMENT_EDIT`.
6. **Actes réservés au `SUPER_ADMIN`** : création et modification d'un compte, attribution ou retrait d'un rôle, changement de statut, matrice des permissions, décision finale sur une bourse.
7. **Auto-modification interdite** : personne ne peut modifier ses propres rôles ni son propre statut (403).
8. **Dernier super administrateur** : le retrait du rôle `SUPER_ADMIN` au dernier super administrateur actif est refusé.
9. **Périmètre formateur** : un formateur ne voit que les groupes où il est affecté, leurs séances, présences et cahiers de texte ; il ne peut pas écrire dans les groupes des autres.

### 4.4 Matrice de synthèse des accès

| Module | SUPER_ADMIN | ADMIN | DIRECTION | ASSISTANT_ADMIN | SECRETAIRE | RESP_PEDA | FORMATEUR | ETUDIANT |
|---|---|---|---|---|---|---|---|---|
| Visites / prospects | Lecture | Lecture | Écriture | Écriture | Écriture | — | — | — |
| Dossiers étudiants | Lecture | Lecture | Écriture | Lecture | Écriture | — | — | Son dossier |
| Inscriptions | Lecture + édition + validation | Lecture + édition | Création + édition + validation | Lecture + validation | Création + édition | Lecture + validation | — | Ses inscriptions |
| Catalogue / modules / leçons | Lecture | Lecture | Écriture | — | Lecture | Écriture | Écriture (modules/leçons) | — |
| Groupes | Écriture | Écriture | Écriture | — | Lecture | Écriture | Ses groupes | Ses groupes |
| Séances / présences | Lecture | Lecture | Écriture | — | Lecture | Écriture | Ses séances | Ses présences |
| Ressources | Lecture | Lecture | Écriture | — | — | Écriture | Écriture | Publiées |
| Caisse / journal | Écriture | Écriture | Écriture | Écriture | — | — | — | — |
| Paiements étudiants | Écriture | Écriture | Écriture | Écriture | Écriture | Écriture | — | Reçus de ses paiements |
| Supervision financière | Lecture / export | Lecture / export | — | — | — | — | — | — |
| Utilisateurs / rôles | Écriture | Lecture | — | — | — | — | — | — |
| Journal d'audit | Lecture | Lecture | — | — | — | — | — | — |
| Réglages / années | Écriture | Écriture | Écriture | — | — | — | — | — |
| Demandes d'accès | Traitement | Traitement | Traitement | Traitement | Traitement | Traitement | — | — |
| Bourses | Décision | Lecture | — | — | — | — | — | Suivi public |

> **Lecture** : l'écran est accessible, l'écriture ne l'est pas. **—** : aucun accès à l'écran. Les rôles `COMPTABLE` et `ACCUEIL`, conservés pour l'historique, ne figurent pas dans cette matrice.
>
> La matrice fine (19 droits) est éditable par le `SUPER_ADMIN` dans `/dashboard/super-admin/permissions/`. Les décorateurs de rôle restent la première barrière ; à ce jour, seul le droit `finance.write` pilote une action (l'encaissement des paiements étudiants), les autres droits étant enregistrés sans être encore branchés. **Au 10/11/2026**, ce droit est porté en base par `DIRECTION`, `ASSISTANT_ADMIN`, `SECRETAIRE`, `RESP_PEDA`, `SUPER_ADMIN` et `ADMIN` (ainsi que par l'ancien rôle `COMPTABLE`) : le secrétariat et la supervision pédagogique peuvent donc encaisser un paiement étudiant tant que la matrice n'est pas resserrée.

### 4.5 Permissions fines

| Clé | Libellé |
|---|---|
| `users.read` | Lire les utilisateurs |
| `users.create` | Créer des utilisateurs |
| `users.edit` | Modifier des utilisateurs |
| `roles.manage` | Gérer les rôles |
| `access_requests.review` | Examiner les demandes d'accès |
| `students.read` | Lire les dossiers étudiants |
| `students.write` | Modifier les dossiers étudiants |
| `formations.read` | Lire les formations |
| `formations.write` | Modifier les formations |
| `attendance.read` | Lire les présences |
| `attendance.write` | Saisir des présences |
| `finance.read` | Lire les données financières |
| `finance.write` | Saisir des paiements |
| `scholarship.read` | Lire les candidatures bourse |
| `scholarship.review` | Examiner les candidatures bourse |
| `access_events.read` | Lire le journal des entrées/sorties |
| `access_events.write` | Enregistrer les entrées/sorties |
| `audit.read` | Lire le journal d'audit |
| `certificates.issue` | Délivrer des certificats |

---

## 5. Exigences fonctionnelles

### 5.1 Portail public et accès

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| PF-01 | Page d'accueil publique présentant l'établissement, son offre et les actions de candidature. | M | Réalisé |
| PF-02 | Connexion locale par e-mail **ou** code interne, avec mot de passe. Aucun widget d'authentification externe. | M | Réalisé |
| PF-03 | Inscription publique avec choix d'un rôle demandé parmi les rôles autorisés. Un rôle élevé est refusé. | M | Réalisé |
| PF-04 | Écran de complétion de la demande d'accès pour un compte en attente. | M | Réalisé |
| PF-05 | Approbation ou refus d'une demande, avec rôle effectif, code interne, notification et audit. | M | Réalisé |
| PF-06 | Blocage des comptes en attente, suspendus, désactivés ou refusés, y compris session ouverte. | M | Réalisé |
| PF-07 | Profil : identité, téléphone, adresse, date de naissance, photo, mot de passe, changement d'e-mail par jeton signé. | M | Réalisé |
| PF-08 | Déconnexion et retour au portail public. | M | Réalisé |
| PF-09 | Bandeau de langues français/anglais et sélecteur de thème neutre. | S | Réalisé |

**Règles d'acceptation**

- Un visiteur non authentifié qui demande `/dashboard/` est redirigé vers `/login/`.
- Un compte `PENDING_APPROVAL` ne peut accéder à aucun écran métier.
- Un rôle `SUPER_ADMIN`, `ADMIN` ou `DIRECTION` demandé depuis le formulaire public est refusé sans création de rôle.
- L'approbation ne peut attribuer que les rôles de `REQUESTABLE_ROLES` ; un rôle hors liste est refusé.
- Un approbateur ne peut pas traiter sa propre demande.
- Une demande déjà traitée ne peut pas être rejouée.

### 5.2 Tableaux de bord et files de travail

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| TB-01 | Routage automatique vers le tableau de bord du rôle principal selon l'ordre de priorité des rôles. | M | Réalisé |
| TB-02 | Bande commune « Utilisateurs / Étudiants / Staff » sur les neuf tableaux de bord, alimentée par une source unique. | S | Réalisé |
| TB-03 | Indicateurs propres au rôle : inscriptions en attente, paiements, soldes, recouvrement, formateurs, formations actives. | M | Réalisé |
| TB-04 | Cloche de tâches : inscriptions à valider, demandes d'accès, bourses à instruire, brouillons de caisse, séances planifiées du formateur, notifications non lues. | S | Réalisé |
| TB-05 | Graphiques de tableau de bord alimentés par des séries numériques bornées par période. | C | Réalisé |

**Précision** : les compteurs de la bande commune ne sont pas recopiés dans les cartes des gabarits ; la mesure est centralisée (`core.utils.students_count`, contexte `compteurs`). Les cartes « Étudiants actifs » restent distinctes car elles comptent les comptes approuvés, alors que la bande compte tous les porteurs du rôle étudiant.

### 5.3 Accueil, visites et prospects

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| AC-01 | Enregistrer une visite : contact, type de visiteur, motif, demande, service et personne hôtes, heure d'arrivée, agent. | M | Réalisé |
| AC-02 | Réutiliser un contact existant par recherche téléphone/e-mail/nom, ou en créer un. | M | Réalisé |
| AC-03 | Clôturer une visite par l'heure de départ ; statut `IN_PROGRESS` tant qu'elle est présente. | M | Réalisé |
| AC-04 | Convertir une visite en prospect, puis un prospect en étudiant (rôle secrétariat pour la conversion étudiant). | M | Réalisé |
| AC-05 | Gérer les motifs de visite (libellé, ordre, actif/inactif). | S | Réalisé |
| AC-06 | Gérer un prospect : source, formation visée, domaine, niveau, programme linguistique, contact préféré, statut, prochaine relance. | M | Réalisé |
| AC-07 | Enregistrer les relances : type de contact, résumé, informations données, résultat, prochaine action et date. | M | Réalisé |
| AC-08 | Afficher l'historique d'audit de chaque visite et de chaque prospect. | S | Réalisé |

**Règles d'acceptation**

- Une visite porte une référence unique `VIS-AAAA-NNNN`.
- Un prospect porte une référence unique `PRO-AAAA-NNNN`.
- Un contact peut cumuler visites et prospects sans duplication de personne.
- Un prospect converti conserve le lien vers le compte étudiant créé et l'horodatage de conversion.
- Les rôles transversaux consultent mais ne créent ni ne modifient visites, prospects ou motifs.

### 5.4 Secrétariat : étudiants, inscriptions, documents

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| SE-01 | Créer un étudiant (identité, e-mail, téléphone, adresse, date de naissance) avec mot de passe initial facultatif. | M | Réalisé |
| SE-02 | Générer un code interne unique par rôle (`UA-ETU-0001`, etc.). | M | Réalisé |
| SE-03 | Modifier un dossier étudiant sans changer son rôle ni son statut par le formulaire de profil. | M | Réalisé |
| SE-04 | Poser, remplacer ou retirer la photo d'un étudiant ; supprimer du disque le fichier remplacé. | S | Réalisé |
| SE-05 | Téléverser des documents privés (identité, diplôme, relevé, photo, certificat, autre) et les rattacher éventuellement à une inscription. | M | Réalisé |
| SE-06 | Télécharger un document uniquement si l'on est l'étudiant propriétaire ou un membre du staff autorisé. | M | Réalisé |
| SE-07 | Créer une inscription : étudiant, groupe, statut, date de début, tarif, remise, plan de paiement, notes. | M | Réalisé |
| SE-08 | Calculer automatiquement le net dû (`tarif − remise`) et refuser une remise supérieure au tarif. | M | Réalisé |
| SE-09 | Empêcher deux inscriptions identiques (même étudiant, même groupe). | M | Réalisé |
| SE-10 | Valider une inscription : passage du dossier en `ACTIVE`, activation du compte étudiant s'il est en attente et audit. | M | Réalisé |
| SE-11 | Afficher l'historique d'audit du dossier étudiant et de l'inscription. | S | Réalisé |
| SE-12 | Signaler un compte étudiant actif sans aucun dossier d'inscription. | S | Réalisé |
| SE-13 | Filtrer les listes par année académique. | S | Réalisé |

**Règles d'acceptation**

- Un étudiant validé sans groupe ne peut pas être activé : le groupe est obligatoire à la validation.
- Une inscription validée ne crée jamais de doublon de groupe pour le même étudiant.
- Le tarif mensuel de référence d'une formation ne modifie pas les inscriptions déjà créées : leur tarif est figé.
- Une inscription terminée ou annulée renseigne `ended_at` ; une réactivation le remet à vide.
- À la validation, le compte étudiant passe `ACTIVE` et une entrée d'audit `ENROLLMENT_VALIDATE` est écrite ; aucune notification n'est créée à ce stade.
- Le bouton « Encaisser » suit le droit `finance.write` : à la date de référence, le secrétariat et la supervision pédagogique le détiennent comme la direction et l'assistant administratif ; resserrer la matrice ferme l'encaissement sans changer les rôles.

### 5.5 Pédagogie : catalogue, modules et leçons

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| PE-01 | Créer et modifier une formation : nom, domaine, description, durée en mois, frais, tarif mensuel de référence, éligibilité au certificat. | M | Réalisé |
| PE-02 | Archiver une formation et la réactiver sans supprimer ses inscriptions ni son historique. | M | Réalisé |
| PE-03 | **Créer un module manuellement pour une formation donnée**, depuis l'écran « Programmes ». | M | Réalisé |
| PE-04 | **Créer une leçon manuellement pour un module donné**, depuis l'écran « Programmes ». | M | Réalisé |
| PE-05 | Modifier un module et une leçon existants. | M | Réalisé |
| PE-06 | Afficher les modules et leçons dans l'ordre défini, avec leurs heures prévues. | M | Réalisé |
| PE-07 | Auditer chaque création, modification, archivage et réactivation. | S | Réalisé |
| PE-08 | Réserver la gestion du catalogue à `RESP_PEDA` et `DIRECTION` ; les rôles transversaux consultent seulement. | M | Réalisé |
| PE-09 | Réserver la création/modification des modules et leçons à `FORMATEUR`, `RESP_PEDA` et `DIRECTION`. | M | Réalisé |

#### 5.5.1 Création manuelle d'un module (exigence détaillée)

**Parcours**

1. Le responsable pédagogique ouvre `/dashboard/pedagogie/programmes/`.
2. Il repère la formation concernée (ancre `#formation-<id>`).
3. Il déplie le bloc « Ajouter un module ».
4. Il saisit au minimum le titre, éventuellement la description, l'ordre et les heures prévues.
5. Il valide ; le module est créé, un message de succès s'affiche et la page revient sur la formation.

**Champs**

| Champ | Obligatoire | Règle |
|---|---|---|
| Formation | Oui | Pré-remplie par le contexte. L'écran n'offre le formulaire que pour une formation active ; la route dédiée n'a pas de garde serveur sur ce point. |
| Titre | Oui | 200 caractères maximum ; unique au sein de la formation. |
| Description | Non | Texte libre. |
| Ordre | Non | Si vide : `max(ordre des modules de la formation) + 1` ; sinon valeur saisie. |
| Heures prévues | Non | Si vide : `0`. |

**Règles**

- Un module ne peut pas porter le même titre qu'un autre module de la même formation (contrainte `unique_together`).
- L'écran utilise un formulaire natif `<details>` en ligne, sans fenêtre modale ni JavaScript obligatoire.
- Le POST est protégé par le jeton CSRF.
- Un rôle transversal (`SUPER_ADMIN`, `ADMIN`) reçoit un 403 et ne voit pas le formulaire.
- L'action laisse une entrée d'audit `MODULE_CREATE` avec le titre et la formation.
- La redirection cible `#formation-<course_id>`.
- Une route dédiée `/dashboard/pedagogie/modules/nouveau/` reste disponible pour un accès direct.

#### 5.5.2 Création manuelle d'une leçon (exigence détaillée)

**Parcours**

1. Depuis la même page, sous le module concerné, le gestionnaire déplie « Nouvelle leçon ».
2. Il saisit le titre, éventuellement les objectifs, l'ordre et les heures.
3. Il valide ; la leçon est créée et la page revient sur le module.

**Champs**

| Champ | Obligatoire | Règle |
|---|---|---|
| Module | Oui | Pré-rempli par le bloc ; le formulaire en ligne transmet l'identifiant en champ caché. |
| Titre | Oui | 200 caractères maximum ; unique au sein du module. |
| Objectifs | Non | Texte libre. |
| Ordre | Non | Si vide : `max(ordre des leçons du module) + 1` ; sinon valeur saisie. |
| Heures prévues | Non | Si vide : `0`. |

**Règles**

- Un module ne peut pas contenir deux leçons de même titre.
- L'action est auditée `LESSON_CREATE`.
- La redirection cible `#module-<module_id>`.
- Le lien « Modifier » de chaque leçon est affiché aux gestionnaires, y compris pour une leçon créée en ligne.
- Une formation archivée n'affiche pas les formulaires d'ajout.

#### 5.5.3 État de référence et recette

- La base de référence au 10/11/2026 contient 15 formations (7 actives) et **0 module / 0 leçon** : la fonctionnalité est livrée et testée, mais la recette métier doit être conduite avec le responsable pédagogique sur les formations actives.
- Les tests `core/tests/test_pedagogie.py` couvrent la création et la modification par formateur, responsable pédagogique et direction, ainsi que le refus des rôles transversaux en écriture.
- La création en ligne et la création par page dédiée partagent le même formulaire et les mêmes règles.

### 5.6 Pédagogie : groupes, séances, présences, cahier de texte

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| PG-01 | Créer un groupe : nom, formation, dates de début et de fin, horaires, capacité, statut, formateurs. | M | Réalisé |
| PG-02 | Refuser un groupe dont la date de fin ne suit pas la date de début. | M | Réalisé |
| PG-03 | Réserver la création et la modification des groupes à `RESP_PEDA`, `DIRECTION`, `SUPER_ADMIN` et `ADMIN`. | M | Réalisé |
| PG-04 | Un formateur ne voit que les groupes où il est affecté ; la direction, le secrétariat et les rôles transversaux voient tout. | M | Réalisé |
| PG-05 | Planifier une séance : date, horaires prévus et réels, module, leçon, thème, objectifs, contenu, exercices, difficultés, statut. | M | Réalisé |
| PG-06 | Refuser deux séances identiques (même groupe, même date, même heure de début prévue). | M | Réalisé |
| PG-07 | Saisir les présences d'une séance : présent, absent, en retard, excusé, heure d'arrivée, motif, note. | M | Réalisé |
| PG-08 | Ne jamais écraser une présence saisie depuis une autre séance le même jour : la seconde saisie est ignorée et signalée ; la correction depuis la séance d'origine est possible. | M | Réalisé |
| PG-09 | Tenir un cahier de texte par groupe : entrées datées, contenu traité, reste à traiter, prochain contenu, exercices, difficultés, nombre de présents. | M | Réalisé |
| PG-10 | Imprimer le cahier de texte d'un groupe. | S | Réalisé |
| PG-11 | Afficher la progression d'un groupe : heures planifiées, heures réalisées, volume du catalogue. | S | Réalisé |
| PG-12 | Consulter l'historique des présences avec filtres (recherche, statut, formation, formateur, période). | S | Réalisé |
| PG-13 | Un formateur ne peut écrire que dans les séances de ses groupes ; la direction et le responsable pédagogique peuvent écrire partout. | M | Réalisé |
| PG-14 | Le secrétariat consulte les séances et les présences, mais ne les saisit pas. | M | Réalisé |

**Règles d'acceptation**

- Une séance ne peut pas être créée dans un groupe auquel l'utilisateur n'a pas accès.
- Les heures d'une séance sont calculées à partir des horaires réellement saisis, à défaut des horaires prévus ; une durée inconnue reste vide, jamais zéro.
- Le nombre de présents saisi au cahier de texte fait foi ; à défaut, il est déduit de la feuille de présence.
- L'unicité `(enrollment, date)` empêche deux présences distinctes le même jour pour un même étudiant ; la feuille ignore la saisie venue d'une autre séance et permet la correction depuis la séance d'origine.

### 5.7 Pédagogie : ressources et espace étudiant

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| PR-01 | Créer une ressource : titre, description, formation, module, leçon, groupe destinataire, type, fichier ou contenu HTML, échéance, statut. | M | Réalisé |
| PR-02 | Exiger au moins un fichier ou un contenu HTML. | M | Réalisé |
| PR-03 | Refuser un fichier de plus de 10 Mo et les extensions non autorisées. | M | Réalisé |
| PR-04 | Un étudiant ne voit que les ressources publiées, et seulement celles de ses formations/groupes. | M | Réalisé |
| PR-05 | Télécharger ou consulter une ressource via une vue protégée, jamais par une URL de média directe. | M | Réalisé |
| PR-06 | Permettre à l'étudiant de laisser un retour (note de 1 à 5 et commentaire), unique par ressource. | S | Réalisé |
| PR-07 | Permettre au formateur de lire les retours de ses ressources. | S | Réalisé |
| PR-08 | Permettre à l'étudiant de consulter ses présences, ses ressources et ses fiches de cours. | M | Réalisé |
| PR-09 | Permettre à l'étudiant de remplir une fiche de cours après une séance : notions retenues, difficultés, observations, présence, heures suivies. | M | Réalisé |
| PR-10 | Empêcher deux fiches pour la même inscription et la même séance. | M | Réalisé |
| PR-11 | Vérifier que les heures suivies sont cohérentes (début avant fin). | S | Réalisé |
| PR-12 | Imprimer la feuille de suivi d'un étudiant. | S | Réalisé |

### 5.8 Comptabilité et caisse

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| CO-01 | Tenir un journal des écritures avec filtres (recherche, type, statut, catégorie, caisse, moyen, auteur, période) et pagination. | M | Réalisé |
| CO-02 | Exporter la sélection du journal en CSV, avec trace d'audit `FINANCE_EXPORT`. | S | Réalisé |
| CO-03 | Créer une écriture : entrée, sortie ou transfert, catégorie, libellé, montant, date, caisse, caisse de destination, moyen, justificatif, statut, note. | M | Réalisé |
| CO-04 | Refuser un transfert vers la même caisse. | M | Réalisé |
| CO-05 | Refuser une écriture validée datée après aujourd'hui. | M | Réalisé |
| CO-06 | Refuser toute écriture validée qui ferait descendre une caisse sous son plancher (`− découvert autorisé`). | M | Réalisé |
| CO-07 | Laisser les brouillons libres : ils ne comptent pas dans le solde. | M | Réalisé |
| CO-08 | Afficher le disponible d'une caisse au moment du choix et avertir avant une sortie qui consomme au moins le seuil paramétré du disponible. | S | Réalisé |
| CO-09 | Exiger une confirmation explicite pour une sortie au-delà du seuil ; dispenser les recettes et les brouillons. | S | Réalisé |
| CO-10 | Administrer une caisse : nom, type, devise, solde d'ouverture, état, découvert autorisé, archivage, caisse de remplacement. | M | Réalisé |
| CO-11 | Figer le nom et le solde d'ouverture d'une caisse dès qu'elle porte une écriture. | M | Réalisé |
| CO-12 | Refuser toute écriture sur une caisse archivée. | M | Réalisé |
| CO-13 | Gérer les catégories d'écriture par direction (entrée, sortie, transfert), avec désactivation plutôt que suppression si utilisée. | M | Réalisé |
| CO-14 | Ajuster ou réinitialiser une caisse par une écriture contraire motivée, confirmée et auditée ; rien n'est effacé. | M | Réalisé |
| CO-15 | Clôturer une caisse : date, solde d'ouverture, solde théorique, montant compté, écart, note ; une seule clôture par caisse et par date. | M | Réalisé |
| CO-16 | Encaisser un paiement étudiant : inscription, montant, moyen, motif, mois réglé, date d'encaissement, note. | M | Réalisé |
| CO-17 | Refuser un montant supérieur au reste à payer et un paiement en double (clé de soumission). | M | Réalisé |
| CO-18 | Relier chaque paiement à une écriture de caisse et générer une référence `PAY-AAAA...`. | M | Réalisé |
| CO-19 | Générer un reçu imprimable portant l'identité de l'établissement. | M | Réalisé |
| CO-20 | Refuser un paiement daté après aujourd'hui. | M | Réalisé |
| CO-21 | Distinguer la date d'encaissement du mois réglé (`period_year`, `period_month`). | M | Réalisé |
| CO-22 | Calculer les indicateurs uniquement sur les écritures validées ; ne jamais additionner paiements et écritures. | M | Réalisé |
| CO-23 | Supervision financière : toutes les écritures, filtres, totaux validés, soldes, répartition par catégorie, export CSV. | S | Réalisé |
| CO-24 | Auditer la correction d'une écriture (montant, catégorie, libellé, date, motif) et conserver l'écriture remplacée. | M | Réalisé |
| CO-25 | Refuser une correction d'écriture annulée. | M | Réalisé |
| CO-26 | Contrôler la cohérence des relations entre tables (`verifier_relations`, 16 contrôles, lecture seule). | S | Réalisé |
| CO-27 | Contrôler la cohérence financière (`audit_finances`, lecture seule). | S | Réalisé |

**Règles d'acceptation financières**

- Une recette augmente le solde, une sortie le diminue, un transfert est neutre au niveau global et débite la caisse source pour créditer la destination.
- Le solde d'une caisse est calculé à partir de son solde d'ouverture, des entrées validées et des sorties validées ; les brouillons et annulations ne comptent pas.
- Une caisse archivée ne reçoit plus d'écriture ; son solde est figé.
- Le découvert autorisé vaut 0 par défaut ; seul un super administrateur peut le relever, compte par compte.
- Une écriture sans compte est refusée par le champ obligatoire, pas par le contrôle de solde.
- Un paiement partiel ne solde pas un dossier ; un paiement complet le solde ; un trop-perçu est signalé.
- La suppression d'une écriture n'existe pas : on annule, on corrige ou on réinitialise, avec trace.

### 5.9 Bourses

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| BR-01 | Candidature publique : identité, e-mail, téléphone, destination, programme, domaine d'études. | M | Réalisé |
| BR-02 | Téléverser les pièces : identité, diplômes, relevés, photo, lettre de motivation. | M | Réalisé |
| BR-03 | Générer une référence unique `BRS-AAAA-NNNN` et un jeton de suivi. | M | Réalisé |
| BR-04 | Suivre une candidature par sa référence, sans compte. | M | Réalisé |
| BR-05 | Statuts : soumise, en examen, documents demandés, approuvée, rejetée, retirée. | M | Réalisé |
| BR-06 | Le `SUPER_ADMIN` seul décide ; l'`ADMIN` consulte le dossier en lecture seule. | M | Réalisé |
| BR-07 | Auditer la décision de bourse. | M | Réalisé |
| BR-08 | Gérer les destinations proposées. | S | Réalisé |
| BR-09 | Notifier le candidat (e-mail ou notification) à chaque changement de statut. | S | À faire |

### 5.10 Réglages et années académiques

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| RG-01 | Une seule ligne de réglages : nom, signature, adresse, téléphone, e-mail, RCCM, NIU, CNSS, devise, seuil d'alerte. | M | Réalisé |
| RG-02 | Un seul chemin d'écriture pour les réglages ; Django Admin en consultation seule. | M | Réalisé |
| RG-03 | Lire les réglages ne crée jamais la ligne : les valeurs par défaut servent tant que la direction n'a rien enregistré. | M | Réalisé |
| RG-04 | Les gabarits lisent le nom, la devise et les contacts dans un contexte unique ; aucun « FCFA » codé en dur. | M | Réalisé |
| RG-05 | Le seuil d'alerte est borné à 1–100 % ; une valeur hors bornes est refusée à l'écran et en base. | M | Réalisé |
| RG-06 | Année académique : libellé unique, date de début avant date de fin, une seule année « en cours » à la fois. | M | Réalisé |
| RG-07 | Filtrer groupes, étudiants, inscriptions et paiements par année académique. | S | Réalisé |
| RG-08 | Historique des modifications des réglages (avant/après) dans l'audit. | S | Réalisé |
| RG-09 | Identité imprimée sur les reçus et documents (nom, RCCM, NIU, CNSS, coordonnées). | M | Réalisé |

### 5.11 Utilisateurs, rôles, permissions, audit

| ID | Exigence | Priorité | Statut |
|---|---|---|---|
| UT-01 | Lister, rechercher et filtrer les comptes. | M | Réalisé |
| UT-02 | Créer un compte, le modifier, poser sa photo (super administrateur). | M | Réalisé |
| UT-03 | Attribuer et retirer un rôle depuis la fiche utilisateur, avec génération du code interne. | M | Réalisé |
| UT-04 | Changer le statut d'accès depuis la fiche utilisateur. | M | Réalisé |
| UT-05 | Interdire l'auto-modification des rôles et du statut. | M | Réalisé |
| UT-06 | Protéger le dernier super administrateur actif. | M | Réalisé |
| UT-07 | Éditer la matrice postes × permissions. À ce jour, seul `finance.write` est branché sur une action (l'encaissement) ; les autres droits sont enregistrés pour la suite. | S | Partiel |
| UT-08 | Consulter le journal d'audit avec filtres, valeurs avant/après, liens vers l'entité et pagination. | M | Réalisé |
| UT-09 | Afficher l'historique d'audit sur les fiches métier (étudiant, inscription, séance, visite, prospect, opération). | S | Réalisé |
| UT-10 | Notifications : création, marquage lu, compteur, interrogation périodique. | S | Réalisé |
| UT-11 | Django Admin en consultation seule pour les tables financières et les réglages. | M | Réalisé |

**Règles d'acceptation**

- Un rôle ou un statut inconnu est refusé sans écriture ni entrée d'audit.
- Une action sans effet (rôle déjà attribué, statut identique) ne crée pas de doublon d'audit.
- L'activation d'un compte remet `disabled_at` à vide ; toute autre valeur l'horodate.
- Un `ADMIN` voit la fiche utilisateur mais pas les contrôles de rôle/statut et reçoit un 403 sur les routes correspondantes.
- Le journal d'audit ne casse aucun lien sur les identifiants non-UUID (exports, réglages).

---

## 6. Règles de gestion

### 6.1 Identité, comptes et accès

| Code | Règle |
|---|---|
| RG-ID-01 | L'e-mail est l'identifiant principal de connexion (le code interne est aussi accepté) ; il est unique et normalisé en minuscules. |
| RG-ID-02 | Le code interne est unique et généré par préfixe de rôle ; il n'est jamais réattribué à un autre compte. |
| RG-ID-03 | Un compte sans rôle ne voit aucun écran métier et est renvoyé vers l'accueil public. |
| RG-ID-04 | Un rôle élevé (`SUPER_ADMIN`, `ADMIN`, `DIRECTION`) ne peut pas être demandé depuis le formulaire public. |
| RG-ID-05 | L'approbation d'une demande attribue un rôle effectif, distinct du rôle demandé, et le conserve dans `assigned_role`. |
| RG-ID-06 | Un approbateur ne peut attribuer que les rôles de son périmètre : super administrateur et administrateur → tous les rôles demandables ; responsable pédagogique → formateur et étudiant ; direction, assistant administratif et secrétariat → étudiant. |
| RG-ID-07 | Le statut `ACTIVE` est requis pour tout accès métier ; les autres statuts bloquent la session en cours. |
| RG-ID-08 | La suppression d'un compte n'est pas un parcours métier : on désactive ou on suspend. |
| RG-ID-09 | Le changement d'e-mail passe par un jeton signé envoyé à la nouvelle adresse ; en cas d'échec d'envoi, aucune modification n'est enregistrée. |

### 6.2 Étudiants et inscriptions

| Code | Règle |
|---|---|
| RG-ET-01 | Un étudiant est un compte portant le rôle `ETUDIANT`. |
| RG-ET-02 | Un étudiant peut avoir plusieurs inscriptions, dans des groupes différents. |
| RG-ET-03 | Une inscription est unique par couple (étudiant, groupe). |
| RG-ET-04 | Le net dû vaut `tarif − remise`, jamais négatif ; la remise ne peut pas dépasser le tarif. |
| RG-ET-05 | Le tarif et le tarif mensuel d'une inscription sont figés à la création ; un changement de catalogue ne les modifie pas. |
| RG-ET-06 | La validation d'une inscription rend le dossier actif dans le groupe choisi et active le compte étudiant s'il est en attente ; le groupe est obligatoire. |
| RG-ET-07 | Une inscription terminée renseigne `completed_at` et `ended_at` ; une inscription annulée ou suspendue renseigne `ended_at` ; une réactivation remet `ended_at` à vide. |
| RG-ET-08 | Le reste à payer se calcule dossier par dossier ; un trop-perçu sur un dossier ne masque pas la dette d'un autre. |
| RG-ET-09 | Les mois facturables d'une inscription sont les mois civils couverts par la période, bornés par les dates du groupe. |
| RG-ET-10 | La remise est répartie sur les mois facturables ; le reliquat de division est appliqué aux premiers mois. |

### 6.3 Pédagogie

| Code | Règle |
|---|---|
| RG-PE-01 | Une formation archivée reste consultable avec ses inscriptions et son historique ; l'écran de programme n'y propose plus l'ajout de module ou de leçon (la route dédiée reste à durcir côté serveur). |
| RG-PE-02 | Le titre d'un module est unique dans sa formation ; le titre d'une leçon est unique dans son module. |
| RG-PE-03 | L'ordre d'un module ou d'une leçon est facultatif ; à défaut, il prend la place suivante. |
| RG-PE-04 | Les heures prévues sont facultatives ; à défaut, elles valent zéro. |
| RG-PE-05 | Un groupe doit avoir une date de fin postérieure à sa date de début. |
| RG-PE-06 | Un groupe peut avoir plusieurs formateurs ; un formateur ne voit que ses groupes. |
| RG-PE-07 | Une séance est unique par (groupe, date, heure de début prévue). |
| RG-PE-08 | Une présence est unique par (inscription, date) ; une saisie venue d'une autre séance le même jour est ignorée, sans écraser la ligne d'origine. |
| RG-PE-09 | Une fiche de cours étudiant est unique par (inscription, séance). |
| RG-PE-10 | Une ressource doit porter un fichier ou un contenu HTML ; un étudiant ne voit que les ressources publiées. |
| RG-PE-11 | Un retour étudiant est unique par (ressource, étudiant). |
| RG-PE-12 | Le nombre de présents du cahier de texte fait foi ; à défaut, il est déduit des présences. |
| RG-PE-13 | Un document étudiant n'est téléchargeable que par son propriétaire ou un membre du staff autorisé. |

### 6.4 Caisse et paiements

| Code | Règle |
|---|---|
| RG-FI-01 | Toute recette ou dépense significative passe par une `CashTransaction`. |
| RG-FI-02 | Le solde d'une caisse = solde d'ouverture + entrées validées − sorties validées. |
| RG-FI-03 | Un transfert ne modifie pas le total global : il débite la source et crédite la destination. |
| RG-FI-04 | Une caisse ne peut pas descendre sous `− découvert autorisé` ; la garde est dans le modèle, pas seulement à l'écran. |
| RG-FI-05 | Les brouillons ne comptent pas dans le solde ; ils peuvent exister même si la caisse est à zéro. |
| RG-FI-06 | Une caisse archivée est figée : aucune écriture nouvelle, aucun ajustement. |
| RG-FI-07 | Le nom et le solde d'ouverture d'une caisse sont figés dès qu'elle porte une écriture. |
| RG-FI-08 | Une catégorie utilisée se désactive ; elle ne se supprime pas. |
| RG-FI-09 | Un ajustement ou une réinitialisation passe par une écriture contraire motivée et confirmée ; rien n'est effacé. |
| RG-FI-10 | Une correction d'écriture crée un remplacement et conserve l'original ; une écriture annulée n'est plus corrigeable. |
| RG-FI-11 | Un paiement étudiant ne peut pas dépasser le reste à payer ; un paiement partiel laisse le dossier partiel. |
| RG-FI-12 | Un paiement est relié à une écriture de caisse ; les indicateurs ne comptent que les écritures validées. |
| RG-FI-13 | Une écriture ou un paiement ne peut pas être daté après aujourd'hui. |
| RG-FI-14 | Le mois réglé est distinct de la date d'encaissement ; une mensualité de janvier peut être encaissée en février. |
| RG-FI-15 | Une clôture est unique par (caisse, date) ; l'écart = montant compté − solde théorique. |
| RG-FI-16 | Une sortie qui consomme au moins le seuil paramétré du disponible exige une confirmation explicite. |

### 6.5 Données, audit et intégrité

| Code | Règle |
|---|---|
| RG-DA-01 | Toute action sensible est journalisée avec auteur, action, entité, identifiant, avant/après, IP et horodatage. |
| RG-DA-02 | Le journal d'audit est append-only dans l'usage : on ne le modifie pas depuis l'interface. |
| RG-DA-03 | Les références métier sont uniques et lisibles : `VIS-`, `PRO-`, `PAY-`, `TRX-`, `BRS-`. |
| RG-DA-04 | Les dates et heures sont stockées en UTC et affichées dans le fuseau `Africa/Brazzaville`. |
| RG-DA-05 | Les fichiers privés ne sont jamais servis par une URL de média directe. |
| RG-DA-06 | Les montants sont des entiers non négatifs dans la devise de l'établissement ; la devise d'un paiement déjà enregistré ne change pas. |
| RG-DA-07 | Une suppression de données métier est évitée : on archive, on annule, on désactive. |
| RG-DA-08 | Une année académique « en cours » est unique ; en poser une nouvelle décoche la précédente dans la même transaction. |
| RG-DA-09 | Les réglages tiennent sur une seule ligne (`id = 1`) ; une seconde ligne est refusée en base. |

---

## 7. Parcours et scénarios

### 7.1 Demande d'accès et approbation

1. Le visiteur s'inscrit avec son e-mail, son mot de passe et le rôle souhaité.
2. Le compte est créé en `PENDING_APPROVAL` ; la demande d'accès est enregistrée sans attribution de rôle.
3. Le demandeur est redirigé vers `/pending-approval/` ou complète son rôle via `/demande-acces/`.
4. Un approbateur autorisé ouvre `/dashboard/super-admin/access-requests/`.
5. Il choisit le rôle effectif dans la liste de son périmètre, ajoute une note et approuve ou refuse.
6. En cas d'approbation : le rôle est attribué, le code interne est généré, le compte passe `ACTIVE`, une notification est créée et l'audit est écrit.
7. En cas de refus : le compte passe `REJECTED`, la note est auditée et l'accès reste bloqué.

### 7.2 Prospect → étudiant → inscription → encaissement

1. L'accueil enregistre une visite et éventuellement un prospect.
2. Le prospect est relancé ; son statut évolue.
3. Le secrétariat convertit le prospect en étudiant (compte `ETUDIANT`, code interne).
4. Il crée une inscription sur un groupe, avec tarif, remise et net.
5. La direction, l'assistant administratif, le responsable pédagogique ou le super administrateur valide l'inscription.
6. La comptabilité encaisse un paiement, choisit le mois réglé et le moyen.
7. Le paiement crée une écriture de caisse et un reçu imprimable.
8. L'étudiant apparaît dans le groupe, avec son solde et ses présences.

### 7.3 Création manuelle d'un module et de ses leçons

1. Le responsable pédagogique ouvre « Programmes ».
2. Il sélectionne la formation et déplie « Ajouter un module ».
3. Il saisit le titre, éventuellement la description, l'ordre et les heures.
4. Il valide : le module apparaît dans la formation, l'ancre `#formation-<id>` est conservée et l'audit `MODULE_CREATE` est écrit.
5. Sous le module, il déplie « Nouvelle leçon ».
6. Il saisit le titre, les objectifs, l'ordre et les heures.
7. Il valide : la leçon apparaît sous le module, l'ancre `#module-<id>` est conservée et l'audit `LESSON_CREATE` est écrit.
8. Il peut modifier chaque module ou leçon via les liens dédiés ; chaque modification est auditée.
9. Si la formation est archivée, les formulaires d'ajout disparaissent ; la consultation reste possible.

### 7.4 Séance → présences → cahier de texte → fiche étudiant

1. Le formateur ou le responsable pédagogique planifie une séance dans son groupe.
2. À la séance, le formateur saisit les présences (présent, absent, retard, excusé).
3. Il remplit le cahier de texte : contenu traité, reste à traiter, prochain contenu, exercices, difficultés, nombre de présents.
4. L'étudiant consulte ses présences et remplit sa fiche de cours (notions, difficultés, observations, heures suivies).
5. Le formateur imprime le cahier de texte et la feuille de suivi si nécessaire.
6. La progression du groupe se met à jour à partir des heures planifiées et réalisées.

### 7.5 Clôture de caisse

1. La comptabilité ouvre la clôture d'une caisse à une date.
2. Le solde théorique est calculé à partir des mouvements validés.
3. L'agent saisit le montant compté.
4. L'écart est calculé et affiché.
5. La clôture est enregistrée ; une seconde clôture pour la même caisse et la même date est refusée.
6. Toute correction ultérieure reste une écriture tracée, jamais une modification silencieuse.

### 7.6 Synchronisation horaire des classeurs Google

1. La tâche planifiée Windows déclenche `synchroniser.ps1` toutes les heures.
2. Le script applique les migrations en attente (avec sauvegarde si nécessaire).
3. Il vérifie la présence du JSON de compte de service ; sans JSON, il journalise « Compte de service absent » et sort sans erreur.
4. La commande télécharge les feuilles configurées, classe les classeurs, produit `RAPPORT_ANALYSE.md`.
5. En mode écriture : une copie de la base est posée dans `backups/`, puis les importeurs reconnus sont lancés.
6. Si la base n'a pas changé, la copie est retirée ; si une écriture a eu lieu ou si un importeur échoue, elle est conservée.
7. Le journal d'exécution est écrit dans `synchronisation.log` (rotation à 5 Mo).
8. La base reste la source de service : une panne Google ne bloque pas le guichet.

---

## 8. Modèle de données

### 8.1 Vue d'ensemble

Le modèle compte **37 modèles Django** (dont le modèle utilisateur personnalisé), répartis en huit domaines. Les clés primaires sont des UUID, sauf `PlatformSetting` (entier auto-incrémenté).

| Domaine | Tables |
|---|---|
| Identité et droits | `User`, `Role`, `Permission`, `UserRole`, `RolePermission`, `AccessRequest`, `Notification`, `AuditLog` |
| Réglages | `AcademicYear`, `PlatformSetting` |
| Scolarité | `Course`, `CourseSession`, `Enrollment`, `Attendance`, `StudentSessionNote`, `Certificate` |
| Pédagogie | `Module`, `Lesson`, `SessionRecord`, `Resource`, `ResourceFeedback`, `StudentDocument` |
| Finance | `Payment`, `Expense`, `CashAccount`, `TransactionCategory`, `CashTransaction`, `CashClosure` |
| Accueil | `VisitReason`, `Contact`, `Visit`, `Prospect`, `ProspectFollowUp` |
| Bourses | `Destination`, `ScholarshipApplication`, `ScholarshipDocument` |
| Contrôle d'accès | `AccessEvent` |

### 8.2 Tables principales et champs clés

#### Utilisateurs et droits

| Table | Champs clés | Contraintes |
|---|---|---|
| `User` | `email`, `internal_code`, `account_status`, `password`, `first_name`, `last_name`, `phone`, `address`, `birth_date`, `display_name`, `avatar`, `disabled_at` | E-mail unique, code interne unique, rôle via `UserRole`. |
| `Role` | `key`, `label`, `description`, `is_privileged` | `key` unique. |
| `Permission` | `key`, `description` | `key` unique. |
| `UserRole` | `user`, `role`, `assigned_by`, `assigned_at` | Unique (user, role). |
| `RolePermission` | `role`, `permission` | Unique (role, permission). |
| `AccessRequest` | `user`, `requested_role`, `assigned_role`, `status`, `reviewed_by`, `reviewed_at`, `decision_note` | Statuts `PENDING`, `APPROVED`, `REJECTED`. |
| `Notification` | `user`, `email`, `title`, `message`, `notification_type`, `is_read`, `sent_at` | Types compte, bourse, paiement, général. |
| `AuditLog` | `actor`, `action`, `entity_type`, `entity_id`, `before_summary`, `after_summary`, `ip_address`, `created_at` | Index (entity_type, entity_id), created_at. |

#### Réglages

| Table | Champs clés | Contraintes |
|---|---|---|
| `AcademicYear` | `label`, `start_date`, `end_date`, `is_current` | Libellé unique, fin > début, une seule année en cours (index partiel). |
| `PlatformSetting` | `nom`, `signature`, `adresse`, `telephone`, `email`, `rccm`, `niu`, `cnss`, `devise`, `seuil_alerte`, `mise_a_jour_le` | Une seule ligne (`id = 1`), seuil 1–100. |

#### Scolarité

| Table | Champs clés | Contraintes |
|---|---|---|
| `Course` | `title`, `domain`, `description`, `duration_months`, `fee_amount`, `monthly_fee_amount`, `currency`, `certificate_eligible`, `active` | Montants ≥ 0. |
| `CourseSession` | `name`, `course`, `starts_at`, `ends_at`, `schedule`, `capacity`, `status`, `formateurs` | Fin > début ; statuts planifiée, en cours, terminée, annulée. |
| `Enrollment` | `student`, `session`, `status`, `enrolled_at`, `completed_at`, `start_date`, `ended_at`, `monthly_tariff_amount`, `tariff_amount`, `discount_amount`, `net_amount`, `payment_plan`, `registered_by`, `notes` | Unique (student, session) ; statuts en attente, active, terminée, annulée, suspendue. |
| `Attendance` | `enrollment`, `session_record`, `date`, `status`, `arrival_time`, `absence_reason`, `recorded_by`, `note` | Unique (enrollment, date). |
| `StudentSessionNote` | `enrollment`, `session_record`, `notions_learned`, `difficulties`, `observations`, `attended`, `followed_start`, `followed_end` | Unique (enrollment, session_record). |
| `Certificate` | `enrollment`, `certificate_number`, `issued_at`, `issued_by`, `status` | Unique par inscription, numéro unique. |

#### Pédagogie

| Table | Champs clés | Contraintes |
|---|---|---|
| `Module` | `course`, `title`, `description`, `order`, `planned_hours` | Unique (course, title). |
| `Lesson` | `module`, `title`, `objectives`, `order`, `planned_hours` | Unique (module, title). |
| `SessionRecord` | `session`, `module`, `lesson`, `date`, `planned_start`, `planned_end`, `actual_start`, `actual_end`, `topic`, `objectives`, `content_covered`, `content_remaining`, `next_content`, `exercises_done`, `difficulties`, `notes`, `attendee_count`, `status`, `recorded_by` | Unique (session, date, planned_start). |
| `Resource` | `title`, `description`, `course`, `module`, `lesson`, `session`, `kind`, `file`, `html_content`, `published_at`, `due_date`, `status`, `author` | Formulaire : fichier ou contenu HTML obligatoire, fichier ≤ 10 Mo ; statuts brouillon, publié, archivé. |
| `ResourceFeedback` | `resource`, `student`, `rating`, `comment` | Unique (resource, student) ; note 1–5. |
| `StudentDocument` | `student`, `enrollment`, `doc_type`, `file`, `original_name`, `mime_type`, `size_bytes`, `uploaded_by` | Types identité, diplôme, relevé, photo, certificat, autre. |

#### Finance

| Table | Champs clés | Contraintes |
|---|---|---|
| `Payment` | `enrollment`, `amount`, `currency`, `method`, `submission_key`, `reference`, `status`, `motif`, `period_year`, `period_month`, `paid_at`, `recorded_by`, `transaction` | Référence unique, montant ≥ 1, `submission_key` unique. |
| `Expense` | `category`, `amount`, `currency`, `occurred_at`, `description`, `receipt`, `created_by`, `status`, `transaction` | Modèle hérité, n'alimente plus les indicateurs. |
| `CashAccount` | `name`, `kind`, `currency`, `opening_balance`, `active`, `overdraft_limit`, `archived_at`, `replaced_by` | Nom unique ; type caisse, Mobile Money, banque. |
| `TransactionCategory` | `name`, `direction`, `active` | Unique (name, direction). |
| `CashTransaction` | `reference`, `tx_type`, `category`, `label`, `description`, `amount`, `currency`, `occurred_at`, `account`, `destination_account`, `method`, `counterparty`, `receipt`, `status`, `nature`, `replaces`, `note`, `created_by` | Référence unique, montant ≥ 1, transfert vers un autre compte, plancher de solde. |
| `CashClosure` | `account`, `date`, `opening_balance`, `theoretical_balance`, `counted_amount`, `difference`, `note`, `closed_by` | Unique (account, date). |

#### Accueil, bourses, contrôle d'accès

| Table | Champs clés | Contraintes |
|---|---|---|
| `VisitReason` | `label`, `active`, `order` | Libellé unique. |
| `Contact` | `first_name`, `last_name`, `phone`, `secondary_phone`, `email`, `city`, `notes` | Réutilisable entre visites et prospects. |
| `Visit` | `reference`, `contact`, `visitor_type`, `reason`, `request_description`, `host_service`, `host_person`, `arrival_at`, `departure_at`, `agent`, `status`, `notes` | Référence unique `VIS-`. |
| `Prospect` | `reference`, `contact`, `course`, `domain`, `level`, `language_program`, `desired_start`, `preferred_contact`, `source`, `first_contact_at`, `agent`, `status`, `next_follow_up`, `converted_student`, `converted_at`, `visit` | Référence unique `PRO-`. |
| `ProspectFollowUp` | `prospect`, `occurred_at`, `contact_type`, `phone_used`, `summary`, `info_given`, `course`, `outcome`, `next_action`, `next_follow_up`, `agent` | — |
| `Destination` | `name`, `active` | Nom unique. |
| `ScholarshipApplication` | `reference`, `applicant_user`, `last_name`, `first_name`, `email`, `phone`, `destination`, `program`, `study_domain`, `status`, `reviewed_by`, `review_note`, `tracking_token` | Référence unique `BRS-`, jeton unique. |
| `ScholarshipDocument` | `application`, `document_type`, `file`, `original_name`, `mime_type`, `size_bytes` | Types identité, diplôme, relevé, photo, motivation. |
| `AccessEvent` | `person`, `visitor_label`, `event_type`, `occurred_at`, `recorded_by`, `reason` | Entrée ou sortie. |

### 8.3 Contraintes d'intégrité majeures

- `User.email`, `User.internal_code`
- `Module(course, title)`, `Lesson(module, title)`
- `Enrollment(student, session)`, `Attendance(enrollment, date)`, `StudentSessionNote(enrollment, session_record)`
- `SessionRecord(session, date, planned_start)`
- `ResourceFeedback(resource, student)`
- `Payment.reference`, `CashTransaction.reference`, `Visit.reference`, `Prospect.reference`, `ScholarshipApplication.reference`
- `CashClosure(account, date)`
- `AcademicYear` : fin > début, une seule année `is_current`
- `PlatformSetting` : une seule ligne
- `CashTransaction` : transfert vers un compte différent, plancher de solde

---

## 9. Architecture et choix techniques

### 9.1 Vue d'ensemble

```
Navigateur
   │ HTTPS / HTTP local
   ▼
Django 5.2 (univers_academy)
   ├── Middleware de statut de compte
   ├── URLs publiques, bourses, dashboard
   ├── Vues par domaine (accueil, secrétariat, pédagogie, comptabilité, réglages, supervision)
   ├── Formulaires et modèles
   ├── Services métier (caisse, paramètres, années, imports, relations, sauvegarde, Google Sheets)
   ├── Templates Django + Tailwind compilé
   └── Base de données (SQLite par défaut, PostgreSQL via DATABASE_URL)
```

### 9.2 Composants

| Composant | Rôle |
|---|---|
| `univers_academy/` | Projet Django : `settings.py`, `urls.py`, WSGI. |
| `core/models.py` | 37 modèles, contraintes, propriétés métier et gardes d'écriture. |
| `core/views*.py` | Vues par domaine, contrôle des rôles et des périmètres. |
| `core/forms.py` | Formulaires, validation, calcul du net, formulaires en ligne. |
| `core/decorators.py` | Autorisations serveur. |
| `core/middleware.py` | Blocage des comptes non actifs. |
| `core/taches.py` | Files de travail et notifications de la cloche. |
| `core/caisse.py` | Service d'écriture de caisse, soldes, découvert, ajustements. |
| `core/parametres.py` | Lecture des réglages sans création de ligne. |
| `core/annee_academique.py` | Résolution et filtrage par année. |
| `core/feuille_import.py` | Rapprochement et import du journal de caisse. |
| `core/relations.py` | 16 contrôles de cohérence entre tables. |
| `core/sauvegarde.py` | Copie SQLite et empreinte de base. |
| `core/google_sheets.py` | Téléchargement public ou compte de service, classement des classeurs. |
| `core/management/commands/` | Commandes d'exploitation, d'import, de contrôle et de maintenance. |
| `templates/` | 109 gabarits : public, dashboard, bourses, impressions. |
| `static/` | Tailwind compilé, JavaScript, icônes. |
| `locale/` | Traductions français/anglais. |
| `backups/` | Copies de sécurité SQLite. |
| `docs/` | Documentation, rapports, scripts de génération. |

### 9.3 Pile technique

| Élément | Version / choix |
|---|---|
| Langage | Python 3 |
| Framework | Django ≥ 5.1, < 6.0 (5.2 installé) |
| Base | SQLite en développement et sur poste unique ; PostgreSQL possible via `DATABASE_URL` |
| Driver PostgreSQL | `psycopg2-binary` |
| Front | Templates Django, Tailwind CSS compilé, JavaScript vanilla |
| Images | Pillow, `django-cleanup` |
| Classeurs | `openpyxl` |
| Traductions | `polib`, `gettext` |
| Google | `google-auth`, `requests` |
| Configuration | `python-dotenv`, `dj-database-url` |

### 9.4 Cycle d'une requête

1. Le navigateur appelle une URL.
2. Le middleware vérifie le statut du compte (hors pages publiques, statiques, admin et documents).
3. La vue applique son décorateur de rôle ou de permission.
4. La vue charge les données, applique les filtres d'année et de périmètre.
5. Le formulaire valide les données et les règles métier.
6. Le modèle applique ses gardes (solde, statuts, contraintes).
7. L'action est auditée si elle est sensible.
8. Le gabarit rend la réponse avec le contexte `plateforme`, les compteurs et les notifications.

### 9.5 Conventions de code

- Les textes visibles sont traduits (`gettext`, `{% translate %}`, `{% blocktrans %}`).
- Les variables à points ne sont pas utilisées dans un `{% blocktrans %}` (rendu vide sans erreur) ; on passe par `{% with %}`.
- Les formulaires détectent un objet neuf via `_state.adding`, jamais via `pk` (les UUID sont générés à l'instanciation).
- Les vues qui mélangent lecture et écriture portent un garde explicite.
- Les montants sont formatés avec la devise lue dans les réglages, jamais codée en dur.
- Les fichiers privés passent par une vue de service authentifiée.

---

## 10. Intégration Google Sheets

### 10.1 Sources

Deux classeurs sont configurés par défaut :

| Feuille | Identifiant | Usage |
|---|---|---|
| Classeur 1 | `1skjUY883GPpTOlG9nYP_Z6PrAj60rQ47NvTfpRYygCU` | Base élèves / journal selon les onglets |
| Classeur 2 | `1GmjRV7T1dcLCD9kQd_hphdYLrO1Z6ezfgwd9xIA41gU` | Base élèves / journal selon les onglets |

La liste peut être remplacée par la variable `CLASSEURS_GOOGLE_IDS` ou par des options `--feuille` répétées.

### 10.2 Authentification

Deux voies sont possibles :

1. **Export public anonyme** : la feuille est partagée « Tout utilisateur disposant du lien → Lecteur ». Rapide, mais toute personne ayant le lien lit les données. À réserver aux démonstrations.
2. **Compte de service** (recommandé) : un robot Google avec sa propre adresse `...@....iam.gserviceaccount.com` reçoit le partage en lecture. Le JSON est stocké hors dépôt, par défaut dans `~/.config/academy/service-account.json`. Les scopes sont `drive.readonly` et `spreadsheets.readonly`.

Le chemin peut être surchargé par `GOOGLE_APPLICATION_CREDENTIALS` ou `--credentials`.

### 10.3 Chaîne de synchronisation

| Étape | Commande / composant | Effet |
|---|---|---|
| 1 | `manage.py migrer` | Applique les migrations en attente ; sauvegarde SQLite seulement si une migration attend. |
| 2 | `manage.py etat_google` | Affiche le chemin du JSON, le `client_email`, le projet et l'état d'accès de chaque feuille, sans télécharger. |
| 3 | `manage.py synchroniser_classeurs` | Télécharge, classe, analyse ; **n'écrit rien en base**. |
| 4 | `manage.py synchroniser_classeurs --ecrire` | Copie la base, lance les importeurs, retire la copie si rien n'a changé. |
| 5 | `synchroniser.ps1` | Point d'entrée de la tâche planifiée : `migrer` puis synchronisation, journalisée. |
| 6 | `installer_tache_synchronisation.ps1` | Installe ou retire la tâche Windows horaire. |
| 7 | `demarrer.ps1` | `migrer` puis `runserver`. |

### 10.4 Classement des classeurs

| Reconnaissance | Importeur |
|---|---|
| Onglet `Base Etudiants` | `importer_etudiants` |
| Onglet `Enregistrement_Opérations` ou `Feuille 2` | `importer_feuille` |
| Tout le reste | `inconnu`, signalé, non importé |

### 10.5 Fréquence et exploitation

- **Fréquence retenue : toutes les heures**, via la tâche Windows `UniversAcademy - Synchronisation`.
- La tâche tourne sous l'utilisateur courant, en session interactive, pour accéder au JSON stocké dans son profil.
- Elle refuse les lancements simultanés (`IgnoreNew` + verrou PowerShell) et s'arrête au bout de 50 minutes.
- Elle s'exécute avec `-ExecutionPolicy Bypass`.
- Le journal est `synchronisation.log` ; rotation à 5 Mo vers `synchronisation.log.1`.
- Sans JSON, le script journalise « Compte de service absent » et sort sans erreur : la tâche peut rester installée.
- Un échec réel (réseau, partage retiré, conflit d'import) laisse un code de sortie non nul et le détail dans le journal.
- Un import qui entre en conflit avec une saisie applicative s'arrête : `importer_etudiants` refuse d'écraser sans `--efface`.

### 10.6 Sauvegarde avant écriture

- `sauvegarder_base()` copie `db.sqlite3` dans `backups/db_AAAAmmjj_HHMMSS_auto.sqlite3`.
- La copie est posée **avant** les importeurs.
- `empreinte_base()` (date de modification + taille) permet de retirer la copie si la base n'a pas changé.
- Une copie est conservée si une écriture a eu lieu ou si un importeur a échoué.
- Sur PostgreSQL, la copie n'est pas gérée par ce module : elle relève de `pg_dump` et de l'exploitation.

### 10.7 État actuel et condition de mise en service

| Élément | État au 10/11/2026 |
|---|---|
| Tâche horaire | Installée en mode aperçu (`-SansEcrire`). |
| JSON de compte de service | **Absent** de `C:\Users\KLAUZA_DEV\.config\academy\service-account.json`. |
| Feuille 1 | Répond HTTP 401 (privée, non partagée). |
| Feuille 2 | Répond HTTP 200 (publique). |
| Import en écriture | **Bloqué** tant que le JSON n'existe pas et que les deux feuilles ne sont pas partagées avec son `client_email`. |

**Procédure de mise en service**

1. Créer le projet Google Cloud, activer Drive API et Sheets API.
2. Créer le compte de service et télécharger sa clé JSON.
3. Déposer le JSON au chemin par défaut, hors dépôt.
4. Partager chaque feuille avec le `client_email`, rôle Lecteur.
5. Lancer `manage.py etat_google` jusqu'à obtenir un accès complet.
6. Lancer `manage.py synchroniser_classeurs` (aperçu) et lire `RAPPORT_ANALYSE.md`.
7. Réinstaller la tâche sans `-SansEcrire`.
8. Vérifier `LastTaskResult` et `synchronisation.log`.

### 10.8 Critères d'acceptation de l'intégration

- `etat_google` affiche le `client_email` et l'état de chaque feuille sans télécharger de classeur.
- Un aperçu de synchronisation ne modifie ni la base ni `backups/` (hors migrations en attente, traitées séparément par `migrer`).
- Une écriture réelle pose une copie avant les importeurs et la conserve si la base change.
- Une exécution sans changement ne laisse pas de copie supplémentaire.
- Un classeur inconnu est signalé et n'est pas importé.
- Un conflit d'import laisse une trace et un code de sortie non nul.
- La tâche horaire est visible dans `taskschd.msc` et son dernier résultat est consultable.

---

## 11. Sécurité, confidentialité et sauvegardes

### 11.1 Authentification et sessions

- Authentification locale par e-mail ou code interne et mot de passe.
- Mots de passe hachés par Django ; validateurs : similarité, longueur minimale 8, mot de passe courant, entièrement numérique.
- Sessions serveur ; cookie de session `HttpOnly`.
- En production (`DEBUG=False`) : cookies sécurisés, redirection SSL, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`.
- Aucun widget d'authentification externe ; l'ancienne intégration Clerk a été retirée.

### 11.2 Autorisations

- Contrôle serveur systématique, doublé d'un masquage d'interface pour ne pas proposer une action vouée au 403.
- Séparation des pouvoirs : les rôles transversaux lisent tout mais n'écrivent pas le métier courant ; la caisse, les paiements et la création/modification des groupes font exception (voir § 4.3).
- Les actes les plus sensibles (comptes, rôles, statuts, décision de bourse) sont réservés au `SUPER_ADMIN`.
- Le périmètre formateur est limité à ses groupes.
- Les documents privés ne sont accessibles que par leur vue dédiée.

### 11.3 Fichiers et données personnelles

- Les pièces d'identité, diplômes, justificatifs et ressources privées sont stockés sous `media/private/` et servis par une vue authentifiée ; les reçus sont générés à l'affichage, pas stockés.
- Les avatars sont servis par une vue dédiée ; le reste de `media/` n'est pas exposé.
- Les noms, téléphones, adresses, dates de naissance et données financières sont des données personnelles : accès limité au besoin métier.
- Les avatars sont limités à 2 Mo, les fichiers de ressources à 10 Mo ; les pièces étudiantes et de bourse sont contrôlées par extension autorisée.

### 11.4 Journal d'audit

Le journal conserve : acteur, action, type et identifiant d'entité, résumé avant/après, adresse IP, horodatage. Il couvre notamment les créations et modifications de comptes, rôles, statuts, inscriptions, notes, présences, ressources, réglages, écritures de caisse, paiements, exports et décisions de bourse.

### 11.5 Sauvegardes

| Déclencheur | Copie |
|---|---|
| Migration en attente (`migrer`) | `backups/db_...auto.sqlite3` avant `migrate`. |
| Synchronisation en écriture | Copie avant les importeurs, retirée si aucune écriture. |
| Maintenance manuelle | Copie préalable recommandée dans `backups/`. |
| PostgreSQL | `pg_dump` / restauration par l'exploitation. |

**À définir avant production** : durée de rétention, copie hors site, test de restauration, RPO/RTO formalisés.

### 11.6 Points de vigilance avant exposition publique

| Point | Constat | Action attendue |
|---|---|---|
| `DEBUG` | `True` dans l'environnement de développement. | Passer à `False` en production. |
| `SECRET_KEY` | Valeur courte dans le `.env` de développement. | Générer un secret long et unique. |
| HSTS | `SECURE_HSTS_SECONDS` non défini. | Configurer HSTS et HTTPS. |
| Comptes de démonstration | Des comptes de démonstration peuvent subsister en base. | Désactiver ou renouveler leurs accès. |
| Photos de profil | Non redimensionnées ; dépôt limité à 2 Mo. | Redimensionner ou générer une vignette. |
| Authentification forte | Pas de MFA. | À arbitrer selon le risque. |
| Limitation de débit | Pas de limitation sur la connexion. | Ajouter un throttle ou un reverse proxy. |
| Journalisation technique | Pas de supervision centralisée. | Mettre en place un suivi des erreurs et des tâches. |

---

## 12. Exigences non fonctionnelles

| ID | Exigence | Cible | Statut |
|---|---|---|---|
| NFR-01 | Temps de réponse des listes courantes | < 500 ms sur la base de référence | Réalisé (à mesurer en production) |
| NFR-02 | Temps de réponse des tableaux de bord | < 2 s | Réalisé (à mesurer) |
| NFR-03 | Capacité | Plusieurs centaines d'étudiants et plusieurs milliers d'écritures sur SQLite ; PostgreSQL au-delà | Réalisé |
| NFR-04 | Disponibilité | Heures ouvrées ; la base reste servie même si Google est indisponible | Réalisé |
| NFR-05 | Sauvegarde | Copie avant toute écriture automatisée ; RPO ≤ 1 h pour la synchronisation | Réalisé |
| NFR-06 | Restauration | Procédure documentée et testée | Partiel |
| NFR-07 | Traçabilité | Toute action sensible auditée | Réalisé |
| NFR-08 | Internationalisation | Français par défaut, anglais disponible ; aucun mélange de langues au rendu | Réalisé |
| NFR-09 | Accessibilité | Navigation clavier, libellés associés, contrastes Tailwind | Partiel (pas d'audit RGAA) |
| NFR-10 | Compatibilité | Navigateurs modernes (Chrome, Edge, Firefox) | Réalisé |
| NFR-11 | Maintenabilité | Code découpé par domaine, services dédiés, tests automatisés | Réalisé |
| NFR-12 | Observabilité | Journal de synchronisation, audit métier, sorties de commandes | Partiel |
| NFR-13 | Portabilité | SQLite local ou PostgreSQL par variable d'environnement | Réalisé |
| NFR-14 | Sécurité des dépendances | Versions minimales déclarées ; veille sur les vulnérabilités | Partiel (pas de scan automatique ni de verrouillage) |

---

## 13. Contraintes et hypothèses

### 13.1 Contraintes

- L'interface est en français ; les textes doivent rester traduisibles.
- Le back-office est mono-établissement : une seule ligne de réglages.
- Les montants sont entiers, dans la devise de l'établissement ; pas de conversion.
- Le fuseau de référence est `Africa/Brazzaville`.
- Le serveur cible est Windows pour la tâche planifiée actuelle ; un serveur Linux reste possible pour Django, mais la tâche devra être portée (cron/systemd).
- Les classeurs Google restent la source d'alimentation ; l'application ne réécrit jamais dans Google.
- Les parcours métier évitent la suppression : on archive, annule ou désactive. Django Admin reste une porte d'administration distincte pour certaines tables de référence.

### 13.2 Hypothèses

- La direction valide les tarifs, remises et décisions de bourse.
- Le responsable pédagogique dispose des informations de catalogue (modules, leçons, heures).
- Le secrétariat dispose des pièces administratives des étudiants.
- Google Cloud permet de créer un compte de service et de partager les feuilles avec son adresse.
- L'établissement accepte une sauvegarde SQLite locale avant les écritures automatisées.
- Les utilisateurs sont formés à leurs écrans et à leurs périmètres.

---

## 14. Recette et critères d'acceptation

### 14.1 Stratégie de tests

| Niveau | Moyen | Périmètre |
|---|---|---|
| Tests automatisés | `python manage.py test core.tests` | Modèles, formulaires, vues, permissions, imports, synchronisation, sauvegardes. |
| Contrôle système | `python manage.py check` | Configuration Django. |
| Contrôle des migrations | `python manage.py migrer --verifier` | `check`, `makemigrations --check --dry-run`. |
| Contrôle des relations | `python manage.py verifier_relations` | 16 contrôles, lecture seule, portique `--maxi 0`. |
| Contrôle financier | `python manage.py audit_finances` | Trop-perçus, paiements sans caisse, écarts, soldes négatifs, dates futures. |
| Contrôle des privilèges | `python manage.py audit_privileges` | Attributions de rôles à vérifier. |
| Contrôle i18n | `python manage.py verifier_i18n --maxi 0` | Messages balisés et traduits. |
| Recette manuelle | Navigateur | Parcours par rôle, impressions, refus 403. |
| Tests end-to-end | Non automatisés | À prévoir si le besoin de non-régression visuelle augmente. |

### 14.2 État des tests

- **684 tests** exécutés avec succès sur la base de test créée par Django (dernière exécution connue au 10/11/2026).
- `manage.py check` : aucun problème.
- La base de production n'est jamais touchée par les tests.
- Les tests couvrent notamment : portail, authentification, rôles, profils, visites, prospects, étudiants, inscriptions, pédagogie, comptabilité, permissions, supervision, bourses, réglages, années académiques, imports, synchronisation, sauvegardes, relations et rendu bilingue.

### 14.3 Scénarios d'acceptation

| Scénario | Résultat attendu |
|---|---|
| Un visiteur s'inscrit avec le rôle « Formateur » | Compte en attente, demande enregistrée, aucun rôle attribué. |
| Un super administrateur approuve la demande | Rôle attribué, code interne généré, notification, audit, accès autorisé. |
| Un `ADMIN` tente de modifier un rôle | 403, aucun changement, aucun audit trompeur. |
| Le responsable pédagogique crée un module | Module visible sous la formation, ordre suivant, audit `MODULE_CREATE`, retour sur l'ancre. |
| Le responsable pédagogique crée une leçon | Leçon visible sous le module, ordre suivant, audit `LESSON_CREATE`, retour sur l'ancre. |
| Un `ADMIN` tente de créer un module | 403, formulaire absent. |
| Le secrétariat crée une inscription avec remise > tarif | Refus, message explicite, aucune écriture. |
| La direction valide l'inscription | Compte étudiant actif, groupe rattaché, audit `ENROLLMENT_VALIDATE`. |
| La comptabilité encaisse plus que le reste à payer | Refus. |
| Une sortie vide la caisse au-delà du découvert | Refus avec montant manquant, y compris par script. |
| Un transfert vers la même caisse | Refus. |
| Un formateur saisit une présence depuis deux séances différentes le même jour | La seconde saisie est ignorée, la ligne d'origine est conservée. |
| Un étudiant tente de lire une ressource brouillon | 404/403, aucune fuite. |
| Un utilisateur non autorisé télécharge un document | 404, aucune fuite. |
| La tâche horaire tourne sans JSON | Sortie propre, journal « Compte de service absent », pas d'erreur. |
| La synchronisation écrit puis échoue | Copie de sécurité conservée, code de sortie non nul. |
| La synchronisation ne change rien | Copie de sécurité retirée, pas d'empilement dans `backups/`. |

### 14.4 Définition de « terminé »

Une exigence est considérée terminée lorsque :

1. le parcours est disponible dans l'interface ;
2. les contrôles serveur sont en place et testés ;
3. les règles de gestion sont appliquées par le modèle ou le service ;
4. l'action sensible est auditée ;
5. les tests automatisés passent ;
6. la documentation d'exploitation est à jour ;
7. la recette métier est signée par le responsable du domaine.

---

## 15. Exploitation et déploiement

### 15.1 Prérequis

- Python 3 et environnement virtuel.
- Dépendances `requirements.txt`.
- Base SQLite (`data/db.sqlite3`) ou `DATABASE_URL` PostgreSQL.
- Variables d'environnement : `SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `TIME_ZONE`, paramètres e-mail.
- Pour Google : JSON de compte de service et partage des feuilles.
- Pour la tâche Windows : session interactive de l'utilisateur, accès au JSON.

### 15.2 Commandes usuelles

```powershell
# Démarrage local (migrations + serveur)
.\demarrer.ps1

# Contrôle de configuration
.\.venv\Scripts\python.exe manage.py check

# Migrations avec sauvegarde conditionnelle
.\.venv\Scripts\python.exe manage.py migrer
.\.venv\Scripts\python.exe manage.py migrer --verifier

# Diagnostic Google
.\.venv\Scripts\python.exe manage.py etat_google

# Synchronisation en aperçu
.\.venv\Scripts\python.exe manage.py synchroniser_classeurs

# Synchronisation en écriture
.\.venv\Scripts\python.exe manage.py synchroniser_classeurs --ecrire

# Contrôles de cohérence
.\.venv\Scripts\python.exe manage.py verifier_relations
.\.venv\Scripts\python.exe manage.py audit_finances
.\.venv\Scripts\python.exe manage.py audit_privileges

# Tests
.\.venv\Scripts\python.exe manage.py test core.tests
```

### 15.3 Tâche horaire Windows

```powershell
# Installation en aperçu (aucune écriture)
.\installer_tache_synchronisation.ps1 -SansEcrire

# Installation en écriture
.\installer_tache_synchronisation.ps1

# Choisir l'heure du premier passage
.\installer_tache_synchronisation.ps1 -Heure 07:30

# Vérifier
Get-ScheduledTaskInfo -TaskName "UniversAcademy - Synchronisation" |
  Select-Object LastRunTime, LastTaskResult, NextRunTime

# Retirer
.\installer_tache_synchronisation.ps1 -Desinstaller
```

Si PowerShell bloque l'exécution des scripts :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\installer_tache_synchronisation.ps1
```

### 15.4 Sauvegarde et restauration

**Sauvegarde**

1. Arrêter l'application ou la tâche de synchronisation.
2. Copier `data/db.sqlite3` dans `backups/` avec un horodatage.
3. Copier également `media/` si les pièces jointes doivent être conservées avec la base.
4. Vérifier la taille et l'ouverture de la copie.

**Restauration**

1. Arrêter l'application.
2. Conserver la base fautive sous un autre nom.
3. Copier la sauvegarde choisie vers `data/db.sqlite3`.
4. Lancer `manage.py check` puis `manage.py migrer`.
5. Vérifier les connexions, les soldes et les derniers paiements.

### 15.5 Supervision

- `synchronisation.log` pour la tâche horaire.
- `LastTaskResult` pour le dernier passage.
- Journal d'audit pour les actes métier.
- `verifier_relations`, `audit_finances`, `audit_privileges` pour les contrôles périodiques.
- Sorties des commandes d'import et `RAPPORT_ANALYSE.md` pour les données Google.

---

## 16. Risques et points ouverts

### 16.1 Risques

| Risque | Impact | Mesure |
|---|---|---|
| JSON de compte de service absent | Synchronisation en écriture impossible ; la tâche reste en aperçu. | Fournir le JSON, partager les feuilles, exécuter `etat_google`. |
| Feuille privée non partagée | HTTP 401, import bloqué. | Partager avec le `client_email`, vérifier les API Drive/Sheets. |
| Panne réseau ou quota Google | Pas de rafraîchissement. | La base reste servie ; relancer la tâche ; consulter le journal. |
| Conflit entre saisie applicative et import | Import interrompu. | Le script n'écrase pas sans `--efface` ; arbitrer manuellement. |
| Copie de sauvegarde non testée | Restauration incertaine. | Planifier un test de restauration. |
| SQLite et accès concurrents | Verrous sur écritures simultanées. | PostgreSQL si plusieurs postes écrivent en parallèle. |
| Données historiques incohérentes | Indicateurs faussés, dossiers doubles, trop-perçus. | `verifier_relations` et `audit_finances` ; arbitrage direction ; ne rien corriger automatiquement. |
| Photos non redimensionnées | Transferts lourds, lenteur des listes. | Redimensionner à la pose ou générer une vignette. |
| Absence de tests end-to-end | Régression visuelle ou parcours cassé non détecté. | Ajouter Playwright/Selenium sur les parcours critiques. |
| Secrets de développement | Exposition si déploiement en l'état. | `DEBUG=False`, secret long, comptes de démonstration désactivés, HTTPS/HSTS. |
| État Git non figé | Impossible de reconstruire la version livrée. | Committer et taguer la version de référence. |

### 16.2 Points ouverts (backlog)

| Sujet | État | Décision attendue |
|---|---|---|
| Activation de la synchronisation en écriture | Bloquée par le JSON et le partage. | Fournir les accès Google. |
| Recette métier des modules/leçons | 0 module et 0 leçon en base. | Atelier avec le responsable pédagogique sur les 7 formations actives. |
| Remboursement / annulation d'un paiement | Pas de workflow dédié. | Concevoir le remboursement avec mise à jour du dossier et double audit. |
| Modèle `Expense` hérité | N'alimente plus les indicateurs. | Supprimer ou passer en lecture seule. |
| Exports PDF | Non implémentés. | Arbitrer besoin et moteur de rendu. |
| Statistiques avancées | Totaux de base seulement. | Définir les rapports attendus. |
| Notifications e-mail métier | Non branchées. | Choisir les événements et le fournisseur SMTP. |
| Application des 19 droits fins | Seul `finance.write` pilote une action. | Brancher chaque droit sur ses vues ou assumer explicitement les décorateurs de rôle. |
| Photos de profil | Non redimensionnées. | Choisir redimensionnement à la pose ou vignette. |
| Taille des pièces jointes | Seules les ressources (10 Mo) et les avatars (2 Mo) sont bornés ; les documents étudiants et de bourse ne le sont pas. | Ajouter un plafond aux téléversements de pièces. |
| Contrainte de présence | Une seule présence par étudiant et par date. | Arbitrer le cas de deux séances le même jour. |
| Module sur formation archivée | L'écran masque le formulaire, mais la route dédiée accepte encore une formation archivée. | Ajouter une garde serveur dans `ModuleForm` ou la vue. |
| Rétention des sauvegardes | Non automatisée. | Définir la durée et la copie hors site. |
| Tests end-to-end | Absents. | Planifier leur mise en place. |
| Sécurité de production | `DEBUG`, secret, HSTS, comptes de démo. | Corriger avant exposition. |
| Cohérence de la base réelle | 177 écarts et 39 signalements au 06/11/2026. | Arbitrage direction, correction manuelle tracée. |

> Les écarts constatés sont antérieurs aux garde-fous actuels : 158 recettes « Paiements des étudiants » sans paiement lié (2 986 000 FCFA), 8 dossiers doubles, 3 trop-perçus, 2 mensualités sans mois réglé, 6 comptes étudiants actifs sans dossier ; 30 traces d'audit d'entités disparues et 9 groupes sans formateur sont comptés comme signalements. Rien n'a été corrigé automatiquement.

---

## 17. Livrables et jalons

### 17.1 Livrables

| Livrable | Contenu |
|---|---|
| Application Django | Code source, migrations, commandes, tests. |
| Base de données | Schéma et données de référence. |
| Cahier des charges | Le présent document. |
| Documentation d'architecture métier | `docs/Architecture_metier_Univers_Academy.docx` et son générateur. |
| Documentation d'exploitation | `docs/SYNCHRONISATION_GOOGLE.md`, `docs/Mode_emploi_Univers_Academy.docx`. |
| Documentation d'hébergement | `docs/Hebergement_Univers_Academy.docx` et PDF. |
| Validation métier | `VALIDATION_METIER.md`, rapport de tests. |
| Scripts d'exploitation | `demarrer.ps1`, `synchroniser.ps1`, `installer_tache_synchronisation.ps1`. |
| Rapports de contrôle | `RAPPORT_ANALYSE.md`, sorties de `verifier_relations`, `audit_finances`. |

### 17.2 Jalons proposés

| Jalon | Contenu | Condition de passage |
|---|---|---|
| J1 — Socle | Authentification, rôles, étudiants, inscriptions, caisse. | Tests verts, recette des rôles. |
| J2 — Pédagogie | Catalogue, modules/leçons, groupes, séances, présences, ressources. | Recette avec le responsable pédagogique. |
| J3 — Finance | Paiements, reçus, clôtures, supervision, contrôles. | Soldes justes, audits verts sur base de test. |
| J4 — Google | JSON, partage, aperçu, écriture, tâche horaire. | `etat_google` complet, rapport d'analyse validé. |
| J5 — Production | Sécurité, sauvegardes, restauration, formation. | `DEBUG=False`, secret, HTTPS, comptes de démo désactivés. |

---

## Annexes

### A. Glossaire

| Terme | Définition |
|---|---|
| **Back-office** | Espace authentifié de gestion. |
| **Rôle transversal** | `SUPER_ADMIN` ou `ADMIN`, accès en lecture à tous les modules. |
| **Rôles dissous** | `COMPTABLE` et `ACCUEIL`, conservés pour l'historique mais plus attribuables. |
| **Écriture validée** | Écriture de caisse qui compte dans le solde. |
| **Brouillon** | Écriture de caisse non validée, hors solde. |
| **Découvert autorisé** | Plafond négatif autorisé sur une caisse, fixé par un super administrateur. |
| **Disponible** | Solde + découvert autorisé. |
| **Empreinte de base** | Couple (date de modification, taille) utilisé pour savoir si un import a écrit. |
| **Compte de service** | Identité robot Google utilisée pour lire les feuilles privées. |
| **RPO / RTO** | Perte de données maximale acceptée / délai de remise en service. |

### B. Routes principales

| Domaine | Exemples de routes |
|---|---|
| Public | `/`, `/login/`, `/logout/`, `/register/`, `/demande-acces/`, `/pending-approval/`, `/access-denied/` |
| Bourses | `/bourses/candidature/`, `/bourses/suivi/`, `/bourses/confirmation/<reference>/` |
| Dashboards | `/dashboard/`, `/dashboard/super-admin/`, `/dashboard/admin/`, `/dashboard/direction/`, `/dashboard/secretaire/`, `/dashboard/comptabilite/`, `/dashboard/responsable-pedagogique/`, `/dashboard/formateur/`, `/dashboard/etudiant/`, `/dashboard/accueil/` |
| Accueil | `/dashboard/accueil/visites/`, `/dashboard/accueil/prospects/`, `/dashboard/accueil/motifs/` |
| Secrétariat | `/dashboard/secretaire/etudiants/`, `/dashboard/secretaire/inscriptions/nouvelle/`, `/dashboard/secretaire/inscriptions/<id>/valider/` |
| Pédagogie | `/dashboard/pedagogie/programmes/`, `/dashboard/pedagogie/modules/nouveau/`, `/dashboard/pedagogie/lecons/nouvelle/`, `/dashboard/pedagogie/groupes/`, `/dashboard/pedagogie/seances/`, `/dashboard/pedagogie/presences/`, `/dashboard/pedagogie/cahier-de-texte/`, `/dashboard/pedagogie/ressources/`, `/dashboard/pedagogie/progression/` |
| Comptabilité | `/dashboard/comptabilite/`, `/dashboard/comptabilite/journal/`, `/dashboard/comptabilite/caisses/`, `/dashboard/comptabilite/clotures/`, `/dashboard/comptabilite/paiement/`, `/dashboard/comptabilite/recu/<id>/` |
| Supervision | `/dashboard/super-admin/finances/`, `/dashboard/super-admin/users/`, `/dashboard/super-admin/permissions/`, `/dashboard/super-admin/audit/`, `/dashboard/super-admin/access-requests/`, `/dashboard/super-admin/scholarships/` |
| Réglages | `/dashboard/reglages/parametres-generaux/`, `/dashboard/reglages/annees-academiques/` |
| Fichiers | `/documents/<id>/`, `/media/avatars/<path>` |

### C. Commandes de gestion

| Commande | Rôle |
|---|---|
| `migrer` | Applique les migrations ; sauvegarde si une migration attend ; `--verifier` pour le portique. |
| `etat_google` | Diagnostic du compte de service et de l'accès aux feuilles. |
| `synchroniser_classeurs` | Télécharge, analyse, importe sur `--ecrire`. |
| `analyser_donnees` | Produit le rapport d'analyse d'un dossier de classeurs. |
| `importer_formations` | Importe le catalogue des formations. |
| `importer_etudiants` | Importe élèves, groupes, inscriptions et paiements. |
| `importer_feuille` | Rapproche et importe le journal de caisse. |
| `mettre_en_attente` | Place des comptes en attente selon les classeurs. |
| `regulariser_dates_caisse` | Corrige les dates de caisse futures, avec audit. |
| `verifier_relations` | 16 contrôles de cohérence, lecture seule, portique. |
| `audit_finances` | Contrôles financiers, lecture seule. |
| `audit_privileges` | Contrôles des attributions de rôles. |
| `verifier_i18n` | Contrôle des messages non traduits. |
| `compiler_traductions` | Compile les fichiers de traduction. |
| `seed_roles` | Crée les rôles de référence. |
| `seed_demo` | Jeu de démonstration, mots de passe générés. |
| `purger_donnees_fictives` | Purge encadrée des données de démonstration. |
| `create_superadmin` | Crée un super administrateur initial. |

### D. Variables d'environnement

| Variable | Usage |
|---|---|
| `SECRET_KEY` | Clé secrète Django. |
| `DEBUG` | Mode debug. |
| `DATABASE_URL` | URL de base PostgreSQL ou SQLite. |
| `ALLOWED_HOSTS` | Hôtes autorisés, séparés par des virgules. |
| `TIME_ZONE` | Fuseau, par défaut `Africa/Brazzaville`. |
| `SUPERADMIN_SETUP_SECRET` | Secret de création initiale du super administrateur. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | Configuration SMTP. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Chemin du JSON de compte de service. |
| `CLASSEURS_GOOGLE_IDS` | Identifiants des feuilles, séparés par des virgules. |

### E. Matrice de traçabilité (extrait)

| Exigence | Implémentation | Tests |
|---|---|---|
| PF-02, PF-03, PF-05 | `core/views.py`, `RegisterForm`, `AccessRequest` | `test_public.py`, `test_auth_roles.py` |
| PF-06 | `core/middleware.py`, `active_account_required` | `test_public.py`, `test_permissions.py` |
| SE-07 à SE-10 | `views_secretariat.py`, `EnrollmentForm`, `Enrollment` | `test_secretariat.py`, `test_auth_roles.py` |
| PE-03, PE-04 | `views_pedagogie.module_create/lesson_create`, `ModuleForm`, `LessonForm`, `programs.html` | `test_pedagogie.py` |
| PG-07, PG-08 | `attendance_sheet`, `Attendance` | `test_pedagogie.py` |
| PR-01 à PR-07 | `Resource`, `ResourceForm`, `student_resources` | `test_pedagogie.py` |
| CO-03 à CO-07 | `CashTransaction`, `core/caisse.py` | `test_comptabilite.py` |
| CO-16 à CO-21 | `Payment`, `student_payment_create`, `payment_receipt` | `test_comptabilite.py` |
| CO-23 | `views_supervision.finance_supervision` | `test_supervision.py` |
| CO-26, CO-27 | `core/relations.py`, `audit_finances` | `test_relations.py`, `test_audit_finances.py` |
| RG-01 à RG-05 | `PlatformSetting`, `views_reglages` | `test_parametres.py` |
| RG-06, RG-07 | `AcademicYear`, `core/annee_academique.py` | `test_annee_academique.py` |
| UT-01 à UT-09 | `views.py`, `AuditLog`, `decorators.py` | `test_user_access.py`, `test_permissions.py` |
| Google Sheets | `core/google_sheets.py`, `synchroniser_classeurs` | `test_synchronisation.py` |
| Sauvegarde | `core/sauvegarde.py`, `migrer` | `test_synchronisation.py` |

### F. Documents de référence

| Document | Usage |
|---|---|
| `VALIDATION_METIER.md` | Règles métier, couverture des tests, corrections et points ouverts. |
| `docs/Architecture_metier_Univers_Academy.docx` | Architecture métier détaillée, routes, modèles, audit. |
| `docs/SYNCHRONISATION_GOOGLE.md` | Procédure d'accès Google, tâche horaire, sauvegardes. |
| `docs/Mode_emploi_Univers_Academy.docx` | Mode d'emploi utilisateur. |
| `docs/Hebergement_Univers_Academy.docx` | Contraintes d'hébergement. |
| `RAPPORT_TESTS_2026-11-06.md` (racine) | Rapport de tests. |
| `requirements.txt` | Dépendances. |

---

*Fin du cahier des charges — version 1.0 du 10 novembre 2026.*
