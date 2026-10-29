# Validation métier — Univers Academy

Document de suivi des fonctionnalités implémentées et des tests automatisés.
Dernière exécution : **29/10/2026** — `python manage.py test core.tests` :
**205 tests, 0 échec** (8,3 s sur la base de test).

## 1. Comment lancer les tests

```powershell
D:\Dev\01_Professionnel\Django\academy\env\Scripts\python.exe manage.py test core.tests
```

Les tests utilisent une base de test créée puis détruite par Django : la base de
production `db.sqlite3` n'est jamais modifiée. Les migrations sont appliquées,
y compris `0005_seed_business_defaults` (motifs de visite, catégories
comptables, caisses par défaut), `0006_repair_transaction_counterparty`
(rattrapage des libellés « User object (…) » dans le journal) et
`0007_accessrequest_assigned_role` (rôle effectif attribué lors de
l'approbation). Les rôles sont
créés par le jeu de données de test, comme le fait `manage.py seed_roles` en
production.

## 2. Fonctionnalités livrées par module

### Profil utilisateur
- Consultation et modification des informations personnelles.
- Ajout / suppression d'une photo de profil (JPG, PNG, WebP, 2 Mo max).
- Changement d'adresse e-mail avec confirmation par lien signé valable 24 h.
- L'adresse n'est appliquée qu'après validation du lien ; un échec d'envoi
  affiche une erreur et ne modifie rien.
- Chaque action est historisée dans `AuditLog`.

### Authentification, approbation et attribution des rôles
- Clerk sert uniquement à authentifier (Google ou e-mail/mot de passe). Ses
  métadonnées publiques ne sont jamais lues pour accorder un rôle.
- Toute inscription (locale ou Clerk) crée un compte `PENDING_APPROVAL` sans
  aucun `UserRole`. L'utilisateur choisit un **rôle demandé** lors de
  l'inscription ou sur `/demande-acces/` ; ce rôle est stocké dans
  `AccessRequest.requested_role` et ne donne aucun droit.
- Un compte en attente est bloqué par `AccountStatusMiddleware` : accès refusé
  aux tableaux de bord et à tout écran métier jusqu'à décision.
- Seul un SUPER_ADMIN peut approuver, refuser, suspendre ou révoquer
  (`super_admin_required`). À l'approbation, il choisit le rôle effectif parmi
  `REQUESTABLE_ROLES` (étudiant, formateur, secrétaire, comptable, responsable
  pédagogique, accueil) ; SUPER_ADMIN, ADMIN et DIRECTION sont refusés côté
  serveur même si la valeur est forgée dans le POST.
- La demande conserve `assigned_role`, le décideur, l'horodatage et la note ;
  `AuditLog` enregistre l'action `ACCESS_APPROVE` / `ACCESS_REJECT` avec le
  demandeur, le rôle demandé, le rôle attribué et le statut avant/après.
- Un utilisateur ne peut pas examiner sa propre demande (403), ni modifier son
  propre rôle (403 sur `user_role_assign`), ni changer rôle/statut via le POST
  du profil.
- Initialisation contrôlée : `manage.py create_superadmin` exige
  `SUPERADMIN_SETUP_SECRET` et des identifiants fournis par l'environnement ;
  aucun SUPER_ADMIN ne peut naître d'une inscription ou d'une connexion Clerk.
  `manage.py audit_privileges` (lecture seule) signale les combinaisons
  suspectes sans modifier les données.

### Accueil, visiteurs et prospects
- Enregistrement des visites (contact créé ou réutilisé par téléphone/e-mail),
  heure d'arrivée, départ, motif, service/personne visitée.
- Recherche et filtres sur les visites (texte, statut, dates).
- Conversion d'une visite en prospect sans doublon.
- Création et modification de prospects, relances (`ProspectFollowUp`),
  statut et prochaine date de relance.
- Filtres prospects : recherche, statut, relances du jour/en retard.
- Gestion des motifs de visite (création, activation/désactivation).

### Secrétariat
- Liste et recherche des étudiants (nom, e-mail, code interne, statut, formation).
- Création d'un compte étudiant avec inscription immédiate, génération du code
  interne `UA-ETU-xxxx`, mot de passe initial ou invitation sans mot de passe.
- Conversion d'un prospect en étudiant depuis la fiche prospect.
- Fiche étudiant : inscriptions, paiements, présences, documents, solde.
- Création/modification d'inscriptions avec tarif, remise et montant net.
- Dépôt de documents (10 Mo max) et téléchargement contrôlé (propriétaire,
  secrétariat, direction, comptabilité, super admin).

### Pédagogie (responsable pédagogique / formateur)
- Programmes : modules et leçons (création, modification).
- Séances : compte rendu (horaires prévus/réels, contenu, prochain contenu),
  statut, validation des incohérences horaires.
- Feuille de présences par séance (présent, absent, retard, excusé), motif
  d'absence et heure d'arrivée.
- Une présence déjà saisie pour une autre séance le même jour n'est pas
  écrasée silencieusement.
- Historique des présences, filtres et statistiques simples (totaux, absences
  récurrentes).
- Progression : heures prévues/réalisées, leçons terminées, dernière séance.
- Ressources : support de cours, exercice, devoir ; fichier ou contenu HTML ;
  brouillon/publié/archivé ; visibilité limitée aux étudiants inscrits au
  cours (et au groupe lorsque la ressource est rattachée à une session).
- Espace étudiant : ressources publiées et historique de ses présences.

### Comptabilité
- Journal des opérations avec recherche et filtres (type, caisse, catégorie,
  statut, dates) et export CSV.
- Opérations d'entrée, de sortie et de transfert entre caisses ; contrôles :
  compte destinataire obligatoire et différent, catégorie cohérente avec le
  type.
- Annulation d'opération avec motif obligatoire, historisée.
- Soldes par caisse : ouverture + entrées validées − sorties validées ; un
  transfert est neutre au niveau global.
- Clôtures de caisse : solde d'ouverture, solde théorique, montant compté,
  écart, refus des doublons (même caisse / même date).
- Paiement étudiant : création atomique d'un `Payment` et d'une opération de
  caisse validée liée ; contrôle du reste à payer ; anti double-soumission ;
  un paiement partiel ne solde pas le dossier.
- Reçu imprimable (HTML) accessible au comptable, au secrétariat, à la
  direction et à l'étudiant propriétaire.

### Direction / super administrateur
- Tableaux de bord par rôle et routage automatique selon le rôle principal.
- Journal comptable accessible à la direction.
- Super administrateur : gestion des utilisateurs et consultation du journal
  d'audit.
- Les accès sont vérifiés côté serveur (`role_required`,
  `active_account_required`) et testés par rôle.

### Gestion des rôles et des accès (super administrateur)
- Depuis la fiche utilisateur (`/dashboard/super-admin/users/<id>/`, section
  « Rôles et accès ») : liste des rôles attribués avec bouton **Retirer**, et
  liste déroulante pour **Attribuer** un rôle non encore porté.
- Toujours depuis la même fiche : changement du **statut d'accès**
  (`ACTIVE`, `SUSPENDED`, `DISABLED`, `REJECTED`, `PENDING_APPROVAL`).
  L'activation remet `disabled_at` à vide, toute autre valeur l'horodate.
- Chaque attribution, retrait (`ROLE_ASSIGN` / `ROLE_REMOVE`) et changement de
  statut (`USER_STATUS_CHANGE`, avant/après conservés) est journalisé dans
  `AuditLog` avec l'auteur de l'action.
- Contrôles réservés au SUPER_ADMIN : l'ADMIN voit la fiche mais aucun des
  contrôles, et reçoit un 403 sur les routes `user-role-assign` et
  `user-status-change`.
- Une personne ne peut pas modifier ses propres rôles ni son propre statut
  (403) : la fiche de son propre compte affiche un message explicite.
- Garde-fou de verrouillage : `_is_last_active_super_admin` empêche de retirer
  le rôle SUPER_ADMIN au dernier super administrateur actif (protection
  complémentaire, en plus de l'interdiction d'auto-modification).
- Un rôle ou un statut inconnu est refusé avec un message, sans écriture ni
  entrée d'audit ; une action répétée (rôle déjà attribué, statut identique)
  ne crée pas de doublon d'audit.
- La liste des utilisateurs expose un raccourci « Rôles & accès » vers cette
  section, visible du seul SUPER_ADMIN.

### Supervision financière (super administrateur)
- Espace dédié `/dashboard/super-admin/finances/` (`finance-supervision`) :
  toutes les `CashTransaction` de la base, quel que soit le module d'origine
  (journal, paiements étudiants, dépenses), y compris brouillons et annulations.
- Filtres : recherche (référence, libellé, tiers, description, note, catégorie),
  type, statut, catégorie, caisse/compte, moyen de paiement, auteur, période.
- Totaux calculés sur les seules transactions validées ; soldes des caisses sur
  toutes les périodes ; répartition des sorties par catégorie cliquable.
- Export CSV de la sélection complète (référence, date et heure, montant,
  moyen, caisse, auteur, saisie, statut, justificatif, commentaire, paiement
  ou dépense liés) avec trace d'audit `FINANCE_EXPORT`.
- Écran strictement en lecture : les corrections restent sur la fiche opération
  (motif obligatoire, trace d'audit conservée).
- Tableau de bord super admin : indicateurs réels du mois (entrées, sorties,
  paiements étudiants, salaires et paiements des formateurs), soldes par caisse,
  opérations en attente, paiements incomplets, reste à recouvrer, écarts de
  caisse, transactions récentes cliquables vers la supervision.
- Journal d'audit : filtres (recherche, action, entité, acteur, dates), valeurs
  avant/après lisibles, lien vers l'entité concernée, pagination qui conserve
  les filtres ; les identifiants non-UUID (exports) n'engendrent aucun lien
  cassé.
- Fiche opération : historique d'audit de la transaction, paiement étudiant
  (étudiant, formation, moyen, statut, solde restant) et dépense liée.
- Accès : `role_required('SUPER_ADMIN')` — SUPER_ADMIN et ADMIN (accès
  transversal) ; les autres rôles reçoivent un 403 côté serveur.

### Contrôles de cohérence (lecture seule)
- `manage.py audit_finances` signale, sans rien modifier : trop-perçus par
  dossier, paiements validés sans mouvement de caisse, montants divergents entre
  paiement et caisse, soldes de caisse négatifs. Option `--fail-on-issue` pour
  un code de sortie 1 en supervision automatisée.
- `manage.py audit_privileges` signale les attributions de rôles à vérifier
  (SUPER_ADMIN lié à Clerk, compte inactif avec rôle administratif, etc.).
- Le « reste à recouvrer » des tableaux de bord est calculé dossier par dossier
  (`core.utils.outstanding_receivables`) : un trop-perçu sur un dossier ne
  masque plus la dette d'un autre. Idem pour le solde affiché sur les fiches
  étudiant.
- Les avatars sont servis par une vue dédiée (`core:avatar`, utilisateur actif
  requis), sans exposer le reste de `media/` (pièces justificatives privées).

### Administrateur (accès transversal)
- Rôle `ADMIN` : accès en lecture à tous les modules (accueil, secrétariat,
  étudiants, pédagogie, séances, comptabilité, journal, caisses, vue direction)
  ainsi qu'aux écrans de supervision (utilisateurs, demandes d'accès, bourses,
  journal d'audit).
- Les actes sensibles restent réservés au `SUPER_ADMIN` via
  `super_admin_required` : création et modification d'un compte, attribution ou
  retrait de rôle, validation/refus d'une demande d'accès.
- Ces actions ne sont pas affichées à un `ADMIN` (boutons « Créer un compte »,
  « Modifier », formulaire d'approbation), qui voit un état en lecture seule.
- Tableau de bord ADMIN : indicateurs consolidés — étudiants actifs, demandes
  en attente, formateurs, formations actives, entrées et sorties du mois, solde
  total des caisses, reste à recouvrer des inscriptions en cours, détail des
  soldes par caisse.
- Techniquement : `ELEVATED_ROLES` / `User.is_elevated` ouvrent `role_required`
  et `permission_required` aux rôles `SUPER_ADMIN` et ADMIN ; le menu
  back-office est mutualisé dans `dashboard/admin/_nav.html` (Tableau de bord,
  Utilisateurs, Accueil & visites, Secrétariat, Étudiants, Pédagogie, Séances,
  Comptabilité, Journal, Caisses, Vue direction, Demandes d'accès, Bourses,
  Journal d'audit), le tableau de bord ADMIN regroupe des cartes d'accès direct
  aux modules et la topbar expose une icône « Pilotage » pour les deux rôles
  transversaux (`is_platform_admin`).

### Consultation seule des données métier (SUPER_ADMIN et ADMIN)
- Les deux rôles transversaux voient tout — visites, prospects, étudiants,
  inscriptions, séances, présences, transactions, reçus, ressources — mais
  n'écrivent plus dans le métier. Le décorateur `business_write_required` et
  des gardes explicites sur les vues mixtes renvoient un 403 côté serveur.
- Écritures refusées : visite (création, départ, conversion), prospect
  (création, modification, relance), dossier étudiant et inscription, paiement
  et opération de caisse, clôture, caisse, motifs de visite, compte rendu de
  séance, feuille de présences, ressources, modules et leçons.
- Écritures conservées : comptes utilisateurs, rôles, demandes d'accès et
  décision de bourse (réservée au SUPER_ADMIN ; l'ADMIN consulte le dossier
  avec une mention de lecture seule).
- L'interface masque les boutons et formulaires concernés et affiche une
  mention de consultation ; la navigation et le rendu existants ne changent
  pas pour les rôles métier.
- Chaque fiche métier expose un historique d'audit « qui a fait quoi et
  quand » : étudiant, inscription, séance, visite, prospect, opération de
  caisse. Le journal global propose les mêmes liens vers ces fiches.

## 3. Couverture des tests

| Fichier | Tests | Périmètre |
|---|---:|---|
| `core/tests/test_public.py` | 16 | Landing, login local prioritaire devant Clerk, code interne, inscription avec rôle demandé, refus d'un rôle élevé, comptes en attente/suspendus, déconnexion |
| `core/tests/test_auth_roles.py` | 22 | Clerk sans privilège malgré les métadonnées, onboarding du rôle demandé, approbation/refus réservés au SUPER_ADMIN, rôles élevés refusés, auto-examen et auto-attribution bloqués, comptes suspendus exclus |
| `core/tests/test_profile.py` | 13 | Profil, avatar (upload, suppression, service protégé, fichier absent), e-mail signé (succès, échec d'envoi, jeton invalide/expiré/autre compte) |
| `core/tests/test_accueil.py` | 14 | Visites, contacts réutilisés, départ, conversion, prospects, relances, motifs, recherche |
| `core/tests/test_secretariat.py` | 15 | Étudiants, conversion prospect, inscriptions, remises, doublons, documents |
| `core/tests/test_pedagogie.py` | 25 | Modules/leçons, séances, validations, présences, non-écrasement, ressources, accès étudiant |
| `core/tests/test_comptabilite.py` | 28 | Journal, CSV, opérations, transferts, soldes, clôtures, paiements, reçu, permissions, source unique des soldes et indicateurs |
| `core/tests/test_permissions.py` | 28 | Routage des dashboards, accès croisés, super admin, compte sans rôle, accès transversal de l'ADMIN, lecture seule des deux rôles transversaux sur le métier, décision de bourse réservée au SUPER_ADMIN, historiques par fiche et liens du journal d'audit |
| `core/tests/test_supervision.py` | 10 | Supervision financière (accès, exhaustivité, filtres, totaux, export CSV), indicateurs réels du dashboard super admin, calcul du reste à recouvrer dossier par dossier, historique de transaction, filtres et rendu du journal d'audit |
| `core/tests/test_admin_access.py` | 9 | Accès transversal de l'ADMIN : ouverture de tous les modules, reçu de paiement, document étudiant, catalogue de ressources ; refus (403) sur création/édition de comptes, attribution de rôles et revue de demande d'accès |
| `core/tests/test_audit_finances.py` | 3 | Rapport de cohérence financière : base saine, trop-perçu signalé, paiement sans mouvement de caisse |
| `core/tests/test_user_access.py` | 22 | Fiche utilisateur : présence/absence des contrôles selon le rôle et la cible, ajout/retrait de rôle, rôle et action inconnus, auto-modification bloquée, changement de statut (suspension, réactivation, `disabled_at`, perte d'accès), statut invalide, absence d'audit sans changement, garde-fou du dernier super administrateur actif |
| **Total** | **205** | |

Points explicitement vérifiés :

- persistance réelle des formulaires et présence des entrées d'audit ;
- permissions refusées côté serveur (403) et accès propriétaire ;
- paiement partiel ≠ soldé, surpaiement refusé, double soumission bloquée ;
- transfert de caisse neutre dans le total global ;
- échec d'envoi d'e-mail : aucune modification d'adresse et aucune trace
  trompeuse ;
- clôture : écart calculé et doublon refusé ;
- ressource brouillon invisible pour l'étudiant ;
- document téléchargeable uniquement par l'étudiant propriétaire ou le staff ;
- ADMIN : lecture de tous les modules, refus (403) sur création/modification de
  compte, attribution de rôle et validation d'une demande d'accès, actions
  correspondantes absentes des écrans ;
- SUPER_ADMIN et ADMIN : refus (403) sur toutes les écritures métier (GET des
  formulaires et POST des vues mixtes) et données inchangées après tentative ;
  actions correspondantes absentes des écrans ;
- bourse : l'ADMIN consulte le dossier mais ne peut pas statuer (403, statut
  inchangé) ; le SUPER_ADMIN décide et l'action est auditée ;
- historiques : chaque fiche (étudiant, inscription, séance, visite, prospect,
  opération) affiche l'action et son auteur ; le journal global renvoie vers
  ces fiches par des liens résolus ;
- soldes : `CashAccount.balance` et `account_balance()` donnent le même
  résultat, transferts neutres au niveau global, borne de date respectée ;
- indicateurs : comptabilité et direction calculés uniquement sur les
  `CashTransaction` validées ; un `Payment` ou un `Expense` sans mouvement de
  caisse ne modifie ni les recettes ni les dépenses affichées ;
- supervision : toutes les opérations visibles (validées, brouillons,
  annulées), totaux limités aux validées (aucun double comptage avec
  `Payment`/`Expense`), filtres et export CSV audité ;
- dashboard super admin : indicateurs issus de la base réelle et liens vers les
  listes filtrées correspondantes ;
- journal d'audit : recherche, valeurs avant/après, liens d'entité sans erreur
  sur les identifiants non-UUID (exports), pagination conservant les filtres ;
- fiche opération : historique d'audit et informations du paiement ou de la
  dépense liés ;
- authentification : une connexion Clerk (même avec des métadonnées
  revendiquant SUPER_ADMIN) ne crée aucun rôle et redirige vers la complétion
  du rôle demandé ;
- inscription : le rôle demandé est enregistré sans être attribué ; une
  demande de rôle élevé (SUPER_ADMIN/ADMIN) est refusée ;
- approbation : le formulaire ne propose pas SUPER_ADMIN/ADMIN, présélectionne
  le rôle demandé, affiche l'identifiant Clerk ; l'approbation attribue
  uniquement le rôle choisi, génère le code interne, notifie et écrit l'audit
  (demandeur, rôle demandé, rôle attribué, statut avant/après, décideur) ;
- refus : le compte passe en `REJECTED`, l'accès est bloqué et la note est
  auditée ;
- une demande déjà traitée ne peut pas être rejouée ; un SUPER_ADMIN ne peut
  pas examiner sa propre demande ; un rôle non SUPER_ADMIN reçoit un 403 ;
- falsification : un utilisateur ne peut pas s'attribuer un rôle par POST, un
  SUPER_ADMIN ne peut pas modifier ses propres rôles, le POST du profil ne
  change ni rôle ni statut ni `is_superuser` ;
- suspension : un compte suspendu, rejeté ou désactivé est bloqué, y compris
  sur une session déjà ouverte ; l'approbation prend effet sans reconnexion.

## 4. Corrections de cohérence effectuées

- Formulaires `VisitForm` / `ProspectForm` / `StudentForm` : détection d'un
  objet neuf via `_state.adding` (les clés primaires UUID sont générées dès
  l'instanciation, donc `pk` n'est pas fiable).
- `progression.html` : protection contre une séance sans compte rendu.
- Reçu : `HttpResponseForbidden` retourné correctement (au lieu d'être levé).
- Pédagogie : le secrétariat, autorisé par les décorateurs, peut désormais
  consulter les séances et l'historique des présences (lecture seule) ;
  l'enregistrement des présences lui reste interdit.
- Menu back-office unifié dans `dashboard/admin/_nav.html`, partagé par les
  écrans ADMIN et SUPER_ADMIN ; le lien « Tableau de bord » pointe vers le
  dashboard du rôle connecté.
- Les actions réservées au super administrateur sont masquées pour l'ADMIN au
  lieu de le laisser cliquer vers une page 403.
- Journal comptable : le libellé « Bénéf. / Payeur » affichait
  `User object (<uuid>)`. La migration de données `0005` écrit désormais le nom
  de l'étudiant ; `0006` corrige les opérations déjà enregistrées.
- Règle de solde unique : `CashAccount.movement_totals()` et `balance_at()`
  portent le calcul ; `account_balance()` et la création de clôture s'y
  ramènent. Correction d'un filtre manquant qui faisait additionner à chaque
  caisse toutes les entrées de la plateforme (propriété `.balance`).
- Suppression de `views.payment_create` et `PaymentForm`, non routés, qui
  créaient un paiement sans mouvement de caisse et auraient constitué une
  seconde comptabilité.
- Dashboards comptable et direction : recettes et dépenses calculées uniquement
  sur les `CashTransaction` validées ; un `Payment` ou un `Expense` sans
  transaction liée n'influence plus les indicateurs. L'indicateur mort
  `unpaid_enrollments` (comptage erroné, jamais affiché) est retiré.
- Autorisation d'écriture métier centralisée dans `business_write_required` :
  les rôles transversaux conservent la lecture mais reçoivent un 403 sur les
  actions opérationnelles. Les vues qui mélangent lecture et écriture
  (`visit_detail`, `prospect_detail`, `visit_reasons`, `transaction_detail`,
  `account_list`, `accueil_dashboard`) portent un garde équivalent.
- Fiche inscription : le bouton « Encaisser » n'est plus proposé au secrétariat
  (action comptable) ; il reste visible pour la comptabilité et la direction.
- Modèles de fiche : quatre gabarits avaient perdu leur fermeture de section
  lors de l'ajout de l'historique ; la structure HTML et les balises de bloc
  sont rétablies et couvertes par les tests de rendu.
- Attribution des rôles : le menu d'approbation proposait par défaut le premier
  rôle de l'énumération (`SUPER_ADMIN`) et la vue acceptait n'importe quel
  `role_key` posté, sans persister le rôle attribué. Désormais : liste blanche
  serveur `REQUESTABLE_ROLES` (hors SUPER_ADMIN/ADMIN/DIRECTION), option
  vide par défaut, présélection du rôle demandé, contrôle strict à
  l'approbation et enregistrement de `assigned_role`.
- Inscription et Clerk : aucun rôle demandé n'était recueilli ; le compte
  restait sans demande exploitable. Le formulaire d'inscription, l'écran
  `/demande-acces/` et le routage post-connexion enregistrent maintenant le
  rôle demandé dans `AccessRequest` sans l'attribuer.
- Auto-attribution : un utilisateur connecté pouvait modifier ses propres
  rôles. La vue `user_role_assign` renvoie un 403 sur sa propre fiche ; le POST
  du profil ignore rôle, statut et `is_superuser`.
- Rôles et accès : l'attribution de rôle existait mais n'était pas exposée dans
  le dashboard (il fallait passer par la fiche d'édition). La fiche utilisateur
  porte désormais les contrôles (ajout/retrait de rôle, changement de statut)
  via `user_role_assign` et le nouvel itinéraire `user-status-change`.
  Rôle et statut inconnus sont refusés sans écriture ; une action sans effet ne
  crée pas d'entrée d'audit ; `user_edit` remet `disabled_at` à vide lors d'une
  réactivation.
- `manage.py seed_demo` ne contient plus de mots de passe en dur : ils sont
  générés aléatoirement et affichés une seule fois (ou fournis via
  `DEMO_PASSWORD`).
- Nouvelle migration `0007_accessrequest_assigned_role` (champ
  `AccessRequest.assigned_role`), appliquée sur la base de développement sans
  suppression ni rétrogradation de compte.
- Reste à recouvrer : il était calculé globalement (`max(total dû - total payé,
  0)`), si bien qu'un trop-perçu sur un dossier pouvait masquer la dette d'un
  autre. Le calcul est désormais dossier par dossier via
  `core.utils.outstanding_receivables` (dashboards super admin et admin) et via
  `Enrollment.balance_due` sur les fiches étudiant.
- Avatars : les images étaient stockées sous `media/avatars/` mais aucun
  itinéraire ne les servait (404). Une vue dédiée `core:avatar` les sert aux
  utilisateurs actifs uniquement, sans exposer le reste de `media/`.
- Nouvelle commande `manage.py audit_finances` (lecture seule) : trop-perçus,
  paiements sans mouvement de caisse, montants divergents, soldes négatifs.

## 5. Éléments volontairement non couverts / restants

Ces points ne sont pas déclarés terminés :

- **Maintenance, missions et salaires** : les catégories comptables existent
  (`Maintenance informatique`, `Déplacements et missions`, `Salaires`), mais
  il n'existe pas encore de modèles ni de workflows dédiés (demande,
  validation, pièces jointes, suivi). Les salaires sont suivis par catégorie de
  sortie ; il n'y a pas de masse salariale budgétée permettant de comparer
  prévu et payé.
- **Remboursement / annulation d'un paiement étudiant** : pas de workflow
  dédié ; l'annulation se fait au niveau de l'opération de caisse et ne change
  pas le statut du `Payment` lié. Une correction complète (remboursement avec
  mise à jour du dossier et double trace d'audit) reste à concevoir.
- **Modèle `Expense` hérité** : il n'alimente plus aucun indicateur, mais reste
  éditable dans l'admin Django et peut contenir des lignes sans mouvement de
  caisse. Sa suppression ou son passage en lecture seule reste à décider.
- **Exports PDF** : seul l'export CSV du journal est implémenté ; le reçu est
  imprimable depuis le navigateur.
- **Statistiques avancées** (tableaux de bord analytiques, graphiques) : les
  totaux de base existent, les rapports approfondis ne sont pas développés.
- **Notifications** : le changement d'e-mail gère correctement l'échec
  d'envoi ; les autres notifications métier ne sont pas branchées à un envoi
  réel.
- **Authentification Clerk** : le parcours local et le backend Clerk
  (`sync_clerk_user`, `POST /clerk/session/`) sont testés avec un client Clerk
  simulé (métadonnées ignorées, compte en attente, onboarding) ; l'échange réel
  avec Clerk dépend de clés externes et n'est pas couvert par les tests
  automatisés.
- **Tests navigateur / end-to-end** : vérification manuelle effectuée le
  29/10/2026 dans un navigateur (parcours ADMIN : dashboard, journal, caisses,
  étudiants, reçu, demandes d'accès, utilisateurs, refus 403, export CSV, page
  publique déconnectée ; parcours SUPER_ADMIN le même jour : dashboard
  financier, supervision avec données réelles, journal d'audit filtrable, fiche
  opération et son historique). Aucun test E2E automatisé : les tests du dépôt
  sont des tests Django (vues, formulaires, modèles, permissions).
- **Contrainte de présence** : `Attendance` est unique par
  `(enrollment, date)`. Deux séances le même jour ne peuvent donc pas avoir
  deux présences distinctes pour un même étudiant ; la feuille ignore la
  seconde saisie plutôt que de l'écraser.
- **Anomalie de données constatée le 29/10/2026** : le dossier
  `etudiant@univers.academy` / « Anglais B2 » (net 75 000 FCFA) porte quatre
  paiements validés pour 135 000 FCFA, soit 60 000 FCFA de trop-perçu. Le
  formulaire actuel refuse un montant supérieur au reste à payer ; ces
  encaissements proviennent d'une saisie antérieure au garde-fou. Aucune
  correction automatique n'a été faite : à régulariser manuellement
  (remboursement ou annulation tracée). `manage.py audit_finances` le signale.
- **Sécurité de déploiement** : le `.env` de développement laisse `DEBUG=True`,
  `SECRET_KEY` ne fait que 23 caractères et `SECURE_HSTS_SECONDS` n'est pas
  défini. Les comptes de démonstration (`admin@univers.academy`, superuser,
  `secretaire@…`, `comptable@…`, etc.) ont encore leurs mots de passe par
  défaut actifs : à désactiver ou renouveler avant toute exposition publique.
- **Compte Clerk privilégié** : `japhetsamba52@gmail.com` possède le rôle
  SUPER_ADMIN tout en étant lié à Clerk ; `manage.py audit_privileges` demande
  de vérifier que cette attribution était volontaire.
