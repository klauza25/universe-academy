# Validation métier — Univers Academy

Document de suivi des fonctionnalités implémentées et des tests automatisés.
Dernière exécution : **20/11/2026** — `python manage.py test core.tests` :
**695 tests** (43 s sur la base de test créée par Django ; `db.sqlite3`
de production jamais touché), **0 échec**. L'intégration Clerk a été retirée :
la connexion passe uniquement par le formulaire local (e-mail ou code interne
et mot de passe).

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

### Tableaux de bord (tous les rôles)
- **Une bande de trois compteurs ouvre chaque tableau de bord** : tous les
  comptes, les étudiants, le staff. Le calcul vit dans
  `core.utils.platform_counts()` et le rendu dans la balise `{% compteurs %}`
  (`core/templatetags/ui.py`, gabarit `dashboard/_compteurs.html`) : une seule
  définition à corriger si le périmètre change.
- Le compte des étudiants se prend dans `core.utils.students_count()`, que la
  bande appelle sans restriction et les cartes « Étudiants actifs » avec
  `only_active=True` : les vues n'écrivent plus chacune leur requête, et le
  `distinct()` qui empêche un double rôle d'être compté deux fois est garanti
  par le service. Cette bande reste la seule à afficher ces trois nombres ; les
  cartes qui les répétaient ont été retirées.
- « Utilisateurs » compte tous les comptes, y compris ceux en attente
  d'approbation. « Étudiants » ne retient que les comptes portant le rôle
  étudiant. « Staff » retient tout compte portant au moins un autre rôle : un
  compte sans rôle n'est donc ni étudiant ni staff, et une personne qui cumule
  un rôle étudiant et un rôle d'encadrement apparaît dans les deux.
- La bande est présente sur les neuf tableaux de bord de rôle (super
  administrateur, administrateur, direction, caisse, secrétariat, responsable
  pédagogique, formateur, étudiant, accueil) et n'est pas chargée sur les pages
  publiques ni sur les écrans de travail : aucune requête de comptage inutile.

### Profil utilisateur
- Consultation et modification des informations personnelles.
- Ajout / suppression d'une photo de profil (JPG, PNG, WebP, 2 Mo max).
- **La photo se voit partout où la personne est nommée.** Une balise unique
  (`{% vignette %}`) affiche la photo sur les listes et les en-têtes de fiche —
  étudiants du secrétariat, file de validation, présences du formateur,
  utilisateurs et demandes d'accès du super admin, tableaux de bord ADMIN et
  secrétariat, « Mon profil » — et retombe sur les initiales quand aucune photo
  n'a été posée. Un visage se reconnaît plus vite qu'une suite de lettres.
- **Elle se pose par trois chemins.** L'intéressé sur « Mon profil » ; le
  secrétariat sur la fiche étudiant (écran `.../etudiants/<id>/photo/`, mêmes
  droits que l'écriture sur la fiche) ; le super administrateur sur la fiche du
  compte (écran `.../users/<id>/photo/`). Le personnel doit pouvoir la poser
  parce qu'une fiche sortie des classeurs ne se connecte jamais : sans ces
  écrans, la photo d'un élève pris au centre ne serait visible de personne.
- **La photo remplacée est effacée du disque** (accord de la direction du
  03/11/2026) : sans ce nettoyage, chaque changement laisserait un fichier
  orphelin, la fiche ne montrant que la photo en cours. Le retrait explicite
  rend les initiales.
- Une photo refusée (mauvais format, plus de 2 Mo, aucun fichier) laisse la
  photo en place et affiche la raison du refus ; le dépôt d'une photo ne change
  jamais le statut du compte.
- **Chacun peut changer son mot de passe** sur « Mon profil » : mot de passe
  actuel, nouveau mot de passe, confirmation. Le nouveau doit passer les quatre
  règles du projet (8 caractères minimum, ni trop simple, ni numérique seul,
  pas une variante de vos propres informations). Un dépôt refusé laisse le mot
  de passe en place et affiche la raison.
- **La personne reste connectée sur l'appareil en cours** après le changement ;
  le nouveau mot de passe sert à la prochaine connexion. Une session déjà
  ouverte sur un autre appareil n'est pas révoquée : la déconnexion générale
  suppose un suivi des sessions que le projet n'a pas.
- **Le mot de passe actuel n'est exigé que si le compte en possède un.** Une
  fiche ouverte depuis les classeurs arrive sans mot de passe local : pour ces
  comptes, l'écran sert à en poser un. Le champ reste obligatoire dès qu'un mot
  de passe existe, et un champ vide est refusé.
- Le journal d'audit consigne le changement (`PROFILE_PASSWORD`) avec l'auteur
  et « mot de passe défini avant / après », jamais la valeur du mot de passe.
- Changement d'adresse e-mail avec confirmation par lien signé valable 24 h.
- L'adresse n'est appliquée qu'après validation du lien ; un échec d'envoi
  affiche une erreur et ne modifie rien.
- Comme pour le mot de passe, la preuve par le mot de passe actuel n'est demandée
  qu'aux comptes qui en ont un ; un compte sans mot de passe local change
  d'adresse en confirmant simplement par le lien envoyé à la nouvelle adresse.
- Chaque action est historisée dans `AuditLog` (`PROFILE_AVATAR` pour une pose,
  `PROFILE_AVATAR_DELETE` pour un retrait, `PROFILE_PASSWORD` pour un mot de
  passe, `PROFILE_EMAIL_REQUEST` / `PROFILE_EMAIL_CONFIRM` pour une adresse) avec
  l'auteur de l'action ; la pose par le personnel journalise donc l'agent et la
  personne concernée.

### Authentification, approbation et attribution des rôles
- La connexion est locale : e-mail ou code interne et mot de passe, vérifiés
  côté serveur. Aucun fournisseur d'identité externe n'intervient.
- Toute inscription crée un compte `PENDING_APPROVAL` sans
  aucun `UserRole`. L'utilisateur choisit un **rôle demandé** lors de
  l'inscription ou sur `/demande-acces/` ; ce rôle est stocké dans
  `AccessRequest.requested_role` et ne donne aucun droit.
- Un compte en attente est bloqué par `AccountStatusMiddleware` : accès refusé
  aux tableaux de bord et à tout écran métier jusqu'à décision.
- **Les étudiants naissent en attente d'approbation.** Un compte créé par
  l'import des classeurs, ou au secrétariat avec une inscription restée « en
  attente », est `PENDING_APPROVAL` : il n'est pas compté dans les effectifs et
  n'est pas proposé à la caisse, mais ses inscriptions, ses paiements et ses
  pièces restent consultables. Valider son inscription le passe `ACTIVE` (audit
  `ENROLLMENT_VALIDATE`, clé `compte_approuve`) ; le créer directement avec une
  inscription « Active » vaut approbation immédiate.
- **Aucune approbation n'est retirée automatiquement.** Relancer l'import laisse
  un compte approuvé où il est ; il n'existe aucun classement automatique selon
  l'ancienneté ou la fin de formation. La reprise des fiches déjà écrites par la
  vague du 02/11/2026 s'est faite sur décision : `manage.py mettre_en_attente
  --ecrire --approuver-en-cours` a passé **193 comptes en attente d'approbation,
  dont 66 réapprouvés** car inscrits dans un groupe en cours ou planifié
  (effectif actif : 73 sur 200). La commande ne prend que les comptes étudiants
  auxquels aucun login n'a été distribué (mot de passe vide, donc ouverts depuis
  une fiche de classeur) ; depuis cette reprise elle annonce « réparation déjà
  appliquée » et ne remplace plus rien — les comptes encore actifs sont des
  approbations données après coup. Ni inscriptions, ni paiements, ni pièces n'ont
  été touchés : 187 inscriptions, 580 paiements, 1003 écritures de caisse avant
  comme après (copie `backups/db_20261103_202312_avant_mise_en_attente.sqlite3`).
- Un SUPER_ADMIN ou un ADMIN peut approuver ou refuser une demande d'accès
  (`access_request_review`). L'écran affiche le **rôle suggéré** à la création
  du compte (colonne « Rôle » et liste déroulante présélectionnée) ; le
  décideur valide ce rôle ou en choisit un autre parmi `REQUESTABLE_ROLES`
  (étudiant, formateur, secrétaire, comptable, responsable pédagogique,
  accueil). SUPER_ADMIN, ADMIN et DIRECTION sont refusés côté serveur même si
  la valeur est forgée dans le POST.
- Le tableau de bord ADMIN affiche un panneau « Demandes d'accès en attente »
  avec le rôle suggéré de chaque demandeur.
- La création/modification de comptes et l'attribution de rôles (écran
  « Utilisateurs ») restent réservées au SUPER_ADMIN.
- La demande conserve `assigned_role`, le décideur, l'horodatage et la note ;
  `AuditLog` enregistre l'action `ACCESS_APPROVE` / `ACCESS_REJECT` avec le
  demandeur, le rôle demandé, le rôle attribué et le statut avant/après.
- **Un compte étudiant validé est nécessairement inscrit.** Le formulaire de
  validation comporte un champ « Formation / groupe » (groupes planifiés ou en
  cours) : sans groupe, l'approbation d'un rôle ETUDIANT est refusée et la
  demande reste `PENDING`. Quand le groupe est choisi, l'inscription est créée
  dans la même transaction (statut ACTIVE, tarif = tarif catalogue du cours,
  `registered_by` = décideur) et auditée (`ENROLLMENT_CREATE`, source
  « validation du compte »). L'étudiant apparaît alors dans la liste des
  inscrits et dans le champ « Inscription » du formulaire d'encaissement.
- Si le compte possède déjà une inscription active, la validation n'en crée
  jamais une seconde : le groupe choisi est ignoré et un message le dit ; une
  deuxième inscription se fait au secrétariat.
- Même règle à la création directe d'un compte par le SUPER_ADMIN : le champ
  « Formation / groupe » est obligatoire quand le rôle choisi est étudiant, et
  l'inscription est créée avec le compte (auditée, source « création du
  compte »). Les autres rôles n'en demandent pas.
- Les trois chemins qui peuvent laisser un compte étudiant actif sans
  inscription — attribution du rôle depuis la fiche, édition du compte,
  réactivation par changement de statut — affichent le même avertissement :
  le secrétariat doit inscrire l'étudiant à un groupe pour qu'il paraisse dans
  la liste des inscrits. Aucun ne bloque l'opération et aucun ne choisit un
  groupe à la place du métier : le groupe réel ne peut pas être inventé.
- Un utilisateur ne peut pas examiner sa propre demande (403), ni modifier son
  propre rôle (403 sur `user_role_assign`), ni changer rôle/statut via le POST
  du profil.
- Initialisation contrôlée : `manage.py create_superadmin` exige
  `SUPERADMIN_SETUP_SECRET` et des identifiants fournis par l'environnement ;
  aucun SUPER_ADMIN ne peut naître d'une inscription publique.
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
- Photo de profil : la liste des étudiants et la fiche affichent la photo de
  l'élève (à défaut ses initiales) ; le secrétariat la pose et la retire depuis
  la fiche, aux mêmes conditions que l'écriture sur le dossier.
- Création/modification d'inscriptions avec tarif, remise et montant net.
- Dépôt de documents (10 Mo max) et téléchargement contrôlé (propriétaire,
  secrétariat, direction, comptabilité, super admin).
- La comptabilité consulte la liste des inscrits et les fiches étudiant en
  lecture seule (aucune écriture sur le dossier, boutons masqués).

### Pédagogie (responsable pédagogique / formateur)
- Programmes : modules et leçons (création, modification) par le formateur, le
  responsable pédagogique et la direction ; les rôles élevés consultent sans
  écrire. Chaque création / modification est auditée.
- Groupes de formation (`CourseSession`) : écran `pedagogie/groupes/` listant
  les groupes visibles (période, horaires, formateurs affectés, inscrits /
  capacité, statut), avec création et modification (formation, dates,
  horaires, capacité, statut, formateurs). La gestion est réservée au
  responsable pédagogique et à la direction (`business_write_required`) ; les
  rôles élevés et le formateur y ont accès en lecture, un formateur ne voyant
  que ses propres groupes. La date de fin doit suivre la date de début ; chaque
  création / modification est auditée (`COURSE_SESSION_CREATE` /
  `COURSE_SESSION_EDIT`). C'est l'écran qui manquait pour affecter un formateur
  à un groupe sans passer par l'admin Django.
- **Un groupe qui doit enseigner a un formateur.** La règle vit une seule fois,
  dans `core/groupes.py`, et l'écran Groupes comme l'administration Django
  (`FormuleGroupeAdmin`) l'appliquent : un groupe `Planifiée` ou `En cours`
  enregistré sans aucun formateur est refusé, message posé sur le champ
  « Formateurs », et rien n'est écrit. Un groupe `Terminée` ou `Annulée` y
  échappe : ce sont des archives, souvent reprises des classeurs, et leur
  demander un formateur ferait échouer une simple correction de date. La raison
  est métier : l'étudiant reçoit le contenu du groupe où son inscription le
  place, donc sans formateur personne ne peut y publier une séance ni une
  ressource, et son espace reste vide.
- Les écritures par lot (imports de classeurs) passent par l'ORM et ne peuvent
  pas être tenues par un formulaire : c'est le contrôle `GROUPE_SANS_FORMATEUR`
  de `verifier_relations` qui les montre. Sur la base réelle du 06/11/2026, il
  signale **9 groupes** (8 en cours, 1 planifiée) pour 70 dossiers d'inscription
  actifs, et les deux seuls comptes FORMATEUR portent 2 groupes, tous deux à zéro
  inscrit. Ce tableau de travail se vide en affectant un formateur à chaque
  groupe depuis l'écran Groupes.
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
- Retour étudiant sur une ressource publiée (`ResourceFeedback`) : note de 1 à
  5 et/ou commentaire, soumis depuis la page de lecture ; un étudiant met à
  jour son propre retour sans doublon, uniquement sur les ressources de ses
  formations. Les retours sont visibles du formateur (auteur ou affecté au
  groupe), du responsable pédagogique, de la direction et de l'administrateur
  (lecture seule : 403 côté serveur sur la soumission) ; chaque retour est
  audité (`RESOURCE_FEEDBACK`).
- Espace étudiant : ressources publiées et historique de ses présences.
- Cahier de texte du formateur : après chaque séance, le formateur renseigne
  les notions enseignées, les horaires réellement assurés et le nombre
  d'apprenants ; une feuille imprimable (en-tête Univers Academy, identité
  formateur/filière/classe, tableau dates-heures-notions-effectif-observations
  et totaux) reprend exactement le formulaire papier.
- Fiche de cours de l'apprenant : après chaque séance réalisée, l'étudiant
  confirme sa présence, indique les heures suivies, les notions retenues, ses
  difficultés et ses observations. Une feuille de suivi imprimable par
  formation regroupe ces fiches (dates, heures suivies, notions, présence,
  observations). L'accès est strictement personnel : un étudiant ne voit ni la
  feuille ni la fiche d'un autre parcours, et les rôles élevés n'y ont pas
  accès.

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
- **Une recette ne se date jamais plus tard que le jour de la saisie** :
  l'écran d'encaissement refuse une date postérieure à aujourd'hui et n'écrit
  rien. Sur « Paiements par mois », cocher un mois à venir reste possible —
  c'est une avance — mais la recette se date au jour présent : `paid_at` porte
  le jour où l'argent est entré, `period_year`/`period_month` le mois couvert.
  À l'import des classeurs, une case chiffrée pour un mois qui n'est pas encore
  commencé annonce le plan de la promotion, elle ne prouve pas un encaissement :
  la ligne est signalée (« mensualité d'un mois non encore commencé ») et rien
  n'est porté en paiement. Les écritures déjà enregistrées avant cette règle ne
  sont pas retouchées ; l'audit les signale.
- **Le solde d'une caisse ne passe jamais sous zéro** : la loi est une seule
  fonction, `CashAccount.decouvert()`, appelée par l'écran (`core.caisse.juger`),
  par le service d'écriture (`poster`, `annuler`, `ajuster`, `reinitialiser`,
  `corriger`) et par `CashAccount.save()`. Une sortie, un transfert ou une
  réduction d'entrée validés qui laisseraient la caisse sous son plancher sont
  refusés, avec le montant manquant et le découvert autorisé dans le message —
  même requête envoyée directement à la vue, car le formulaire lit le verdict du
  service au lieu de le recalculer. Annuler une entrée déjà dépensée est refusé
  de la même façon : la régularisation passe par une écriture contraire, pas par
  l'effacement de l'entrée d'origine. Un brouillon reste saisissable (il ne
  compte pas en caisse) et se verra refuser la validation si la trésorerie n'y
  suffit pas. La reprise du journal « Contrôles Mensuels » juge le lot entier
  avant d'écrire : si la caisse choisie finirait sous zéro,
  `importer_feuille --ecrire` refuse et demande la caisse réellement débitée.
- **Le découvert exceptionnel est fermé par défaut** : `overdraft_limit` vaut 0
  sur tous les comptes, et seul un super administrateur le règle sur l'écran
  « Administrer le compte » (la modification est auditée). Un plafond accordé
  abaisse le plancher d'autant ; les écritures concurrentes sont protégées par
  `transaction.atomic()` et une relecture sous verrou de la caisse.
- **Le disponible se lit avant que l'argent ne sorte** : l'écran « Nouvelle
  opération » affiche le solde disponible de chaque caisse active (badge, et le
  choix de la caisse porte ce chiffre dans son libellé) ; une caisse à zéro se
  signale « Solde épuisé » dans la liste des comptes et « Aucun fonds disponible
  » à l'écran de saisie. Une sortie qui consomme au moins 80 % du disponible
  (`core.caisse.avertissement`, seuil `LIMITE_ALERTE`) est annoncée avec le
  pourcentage et exige une case à cocher avant validation ; au-delà du
  disponible, ce n'est plus un avertissement mais le refus du service, pour que
  l'écran ne tienne pas deux discours sur le même argent. La case ne se demande
  ni pour une recette ni pour un brouillon, et un ajustement en baisse obéit à la
  même règle.
- **Un solde ne se corrige jamais en silence** : deux écrans, `Ajuster le solde`
  et `Réinitialiser la caisse`, n'écrivent pas un chiffre — ils posent une
  écriture de nature `ADJUSTMENT` / `RESET`, motivée (motif obligatoire), datée
  du jour, auditée (`CASH_TRANSACTION_CREATE`) et visible dans le journal et
  l'historique du compte. La remise à zéro exige une confirmation explicite,
  montre l'aperçu du solde emporté et signale les brouillons non rapprochés ;
  elle n'efface aucune ligne.
- **Les comptes financiers s'administrent** : type, devise, description, état
  (actif / inactif / archivé) et compte de remplacement se règlent sur
  « Administrer le compte », avec le solde calculé, le disponible, les dix
  dernières opérations et les vingt dernières lignes d'audit. Nom et solde
  d'ouverture restent hors d'atteinte une fois la caisse engagée (les reprises du
  journal désignent les comptes par leur nom). Une caisse archivée refuse toute
  écriture et disparaît des listes de choix.
- **Les catégories d'écriture sont administrables** : création et renommage depuis
  « Catégories », avec le nombre d'écritures attachées et l'historique ; le sens
  (entrée / sortie / transfert) se fixe à la création et ne se rejoue pas, et une
  catégorie se désactive plutôt que de se supprimer — une écriture ne peut pas
  rester sans référence.
- **Une écriture enregistrée se corrige** : « Corriger l'écriture » ajuste le
  montant, la catégorie, le libellé, la date effective et le motif, sur la même
  ligne du journal. Le compte, le sens et le statut ne se touchent pas — une
  écriture mise sur la mauvaise caisse s'annule et se resaisit à côté, pour que
  le journal continue de raconter ce qui est réellement sorti. Une écriture
  annulée n'est plus corrigeable.
- **Mobile Money régularisé le 04/11/2026** : la caisse affichait un creux, deux
  sorties « mois d'octobre » du 30/10/2026 (100 000 et 100 FCFA) ayant été
  enregistrées sur ce portefeuille alors qu'il ne contenait aucune recette.
  Analyse de cause avant correction : les sorties n'étaient pas fausses,
  c'est l'imputation qui l'était — et l'affichage n'avait rien d'un bug.
  Arbitrage de la direction — « ressaisir sur la Caisse principale » : les deux
  sorties restent au journal, annulées et motivées, et reportées sur la caisse
  qui a réellement payé (`TRX-2026-1014`, `TRX-2026-1015`). La caisse affiche
  aujourd'hui +50 000 FCFA, pour une recette étudiante de 50 000 FCFA
  effectivement encaissée dessus. Le plancher de solde interdit désormais ce
  creux.
- L'écran d'encaissement liste aussi les **comptes étudiants actifs sans
  inscription** (« Comptes étudiants sans inscription ») : un paiement exige
  une inscription, donc ces comptes restent visibles plutôt qu'introuvables.
  Le secrétariat et la direction y obtiennent le bouton « Inscrire » ; le
  comptable voit la mention « À inscrire par le secrétariat » (aucun lien
  mort).
- Reçu imprimable (HTML) accessible au comptable, au secrétariat, à la
  direction et à l'étudiant propriétaire.
- Liste des inscrits accessible en consultation à la comptabilité (les
  étudiants apparaissent dès la validation de leur compte, code interne
  `UA-ETU-xxxx` généré automatiquement).

### Année académique (direction)
- Une année académique est une **fenêtre de dates** avec un libellé unique
  (« 2026-2027 ») : la direction la pose elle-même dans `Années académiques`
  (`/dashboard/reglages/annees-academiques/`), avec case « Année en cours ».
  Rien n'est calculé ni inventé par l'application.
- **Une seule année est en cours** : cocher la case décoche la précédente dans
  la même écriture, et la base refuse un second cochage
  (`une_seule_annee_en_cours`) même si on passe devant l'écran. Une fenêtre
  incohérente (dernier jour avant le premier) est refusée par le modèle, donc
  par le formulaire et par la base.
- **Aucune année posée = aucune liste vidée** : les écrans montrent toutes les
  années et un bandeau l'annonce (« Aucune année académique définie : toutes
  les années s'affichent. »). La direction n'a rien coché ? le poste de caisse
  ne reste pas aveugle.
- L'année se juge sur la **date de début du groupe** : un étudiant appartient à
  l'année où son groupe a commencé, une inscription suit la fenêtre de son
  groupe, un dossier annulé ne place personne dans une année. Un compte sans
  inscription n'est d'aucune année : il ne reparaît que sous « Toutes les
  années ».
- Quatre écrans portent le **même sélecteur** et le même mot : liste des
  étudiants (secrétariat), écran d'encaissement simple, grille des douze mois,
  liste des groupes (pédagogie). « Toutes les années » rouvre la liste
  complète ; le filtre survit à une saisie refusée et à la redirection après
  encaissement.
- Un seul chemin d'écriture : l'écran de la direction, **Django Admin en
  consultation seule** (`ConsultationSeule`). Création et réglage sont audités
  (`ACADEMIC_YEAR_CREATE`, `ACADEMIC_YEAR_EDIT`) avec l'année décochée en
  conséquence.

### Paramètres généraux (direction)
- Une **seule ligne de réglages** (`PlatformSetting`, migration `0016`) porte le
  nom de l'établissement, la signature, l'adresse, le téléphone, l'e-mail, les
  trois identifiants légaux (RCCM, NIU, CNSS), le **libellé de devise** et le
  **seuil d'alerte de caisse**. La base refuse toute seconde ligne
  (`parametres_generaux_ligne_unique`) : trois orthographes du nom ne peuvent
  plus coexister sur deux documents officiels.
- **Portée validée par la direction** (arbitrage du 05/11/2026) : nom officiel
  « Universe Academy », coordonnées reprises des documents officiels, et **rien
  de plus** que le seuil et la devise. Aucun tarif, aucun calendrier, aucune
  conversion monétaire.
- Le libellé de devise change **ce qui s'écrit à côté des montants** ; il ne
  convertit rien. Un paiement déjà enregistré garde la devise où il est entré
  (`Payment.currency`, `CashTransaction.currency` ne bougent pas).
- Le seuil d'alerte (1 à 100 %) est la part du solde disponible consommée par
  une sortie qui réclame une confirmation ; il est lu par `core.caisse`, plus
  recopié nulle part. Une valeur hors bornes est refusée à l'écran et en base.
- **Un seul chemin d'écriture** : l'écran `/dashboard/reglages/etablissement/`
  (`PLATFORM_SETTINGS_EDIT`, valeurs avant/après dans l'audit). Django Admin est
  en **consultation seule** sur cette table. Le secrétariat reçoit un 403 ; la
  direction et l'administrateur transversal règlent.
- **Lire n'écrit jamais** : `core.parametres.ligne()` rend une instance non
  sauvée portant les défauts si la direction n'a rien enregistré — une page
  d'accueil ne crée pas la ligne de réglages.
- Les gabarits ne connaissent plus ces mots : ils passent par le contexte
  `plateforme` (`{{ plateforme.nom }}`, `{{ plateforme.devise }}`,
  `plateforme.contacts`). Le mot « FCFA » codé en dur a été balayé des gabarits
  (0 occurrence), des libellés Python et du JavaScript des graphiques, qui lit
  la devise dans `<meta name="devise">` posé par `base.html`.
- Les coordonnées imprimées sortent d'une seule méthode du modèle
  (`PlatformSetting.contacts()`) : le reçu et les trois documents imprimés
  portent désormais la même signature.
- **Garde de rendu** : l'écran des réglages est peint en anglais par
  `test_sans_melange` et ne montre aucune chrome française ; le portique
  `verifier_i18n --maxi 0` est à zéro (1568 messages balisés, 0 sans traduction)
  et les 107 gabarits du projet se compilent tous.
- **Piège mesuré pendant la tranche** : une variable à points dans un
  `{% blocktrans %}` (`{{ plateforme.nom }}`) ne lève aucune erreur et rend
  **vide**. Le titre des fiches de cours avait donc perdu le nom de
  l'établissement sans jamais se plaindre. La correction est un `with n=…` ; un
  test interdit désormais cette écriture dans tous les gabarits.

### Compteurs de la plateforme (bande commune aux neuf tableaux de bord)
- La bande « Utilisateurs / Étudiants / Staff », rendue par `{% compteurs %}` en
  tête de chaque tableau de bord, est **l'unique affiche de ces trois nombres**.
  Les cartes qui les répétaient sont retirées : « Total utilisateurs » et
  « Comptes au total » côté super administrateur, « Étudiants au fichier » côté
  secrétariat — les grilles passent de quatre à trois cartes ; l'accroche du
  secrétariat ne redit plus le nombre d'étudiants, elle garde les dossiers.
- Deux cartes « Étudiants actifs » restent, parce qu'elles ne mesurent pas la
  même chose : la bande compte le rôle étudiant **tous statuts**, la carte
  compte le rôle étudiant **et** le compte approuvé. Le mot « actifs » le dit.
- `core.utils.students_count()` est désormais la seule source de ce compte.
  Avant, quatre vues comptaient chacune de leur côté et trois oubliaient
  `distinct()` : une personne cumulant étudiant et encadrement était comptée
  deux fois. La mesure du jour ne change pas (aucun double rôle en base :
  73 étudiants actifs dans les deux écritures), mais le nombre reste juste quand
  un double rôle arrivera.
- **Garde** : `test_compteurs.py` (5 tests) vérifie la bande sur les neuf
  tableaux et interdit, gabarit en main, qu'une carte ou une carte d'en-tête
  reprenne `total_users`, `total_students` ou `total_staff`.

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
  paiement et caisse, soldes de caisse négatifs, et écritures datées après
  aujourd'hui (`DATE FUTURE` pour un paiement, `CAISSE FUTURE` pour une
  opération de caisse). Chaque famille est listée jusqu'à 20 lignes avec le
  total restant. Option `--fail-on-issue` pour un code de sortie 1 en
  supervision automatisée.
- `manage.py audit_privileges` signale les attributions de rôles à vérifier
  (compte inactif avec rôle administratif, etc.).
- `manage.py verifier_relations` (**16 contrôles des relations entre tables**,
  module `core/relations.py`) juge ce qui est sorti en base, quelle qu'ait été
  la porte d'entrée : écran, Django Admin, import ou script. Paiements sans
  écriture de caisse, recettes d'étudiant sans paiement, paiement en attente
  déjà en caisse, transferts sans destination ou sur leur propre caisse,
  écritures sans compte, net ≠ tarif − remise, remise supérieure au tarif,
  trop-perçus, dossiers doubles, dates futures, mensualités sans mois réglé,
  soldes sous le découvert autorisé, comptes étudiants actifs sans dossier,
  présences orphelines, groupes qui doivent enseigner sans formateur, et traces
  du journal d'audit pointant une entité disparue.
- La commande est **strictement en lecture** (prouvée par test : rien ne bouge
  pendant la mesure) et sert de **portique** : `--maxi 0` par défaut, elle échoue
  dès le premier écart en nommant les codes fautifs. Options `--code` (un seul
  contrôle), `--lignes` (détail borné) et `--json` (compte rendu sur une ligne,
  pour une supervision automatisée).
- Deux points sont des **signalements comptés à part**, et non des refus : les
  traces d'audit d'une entité supprimée (le journal garde l'histoire de la base,
  cela ne la rend pas fausse) et les groupes qui doivent enseigner sans
  formateur (la garde d'écriture ne s'applique qu'aux saisies futures ; les
  groupes sortis des classeurs restent mesurés, pas bloqués).
- Mesure sur la base réelle du 06/11/2026 : **177 écarts et 39 signalements** —
  158 recettes « Paiements des étudiants » sans paiement correspondant
  (2 986 000 FCFA), 3 trop-perçus, 8 dossiers doubles, 2 mensualités sans mois
  réglé, 6 comptes étudiants actifs sans dossier ; en signalements, 30 traces du
  journal et 9 groupes sans formateur (70 dossiers d'inscription actifs). Plus
  aucune écriture datée après aujourd'hui depuis la régularisation des dates de
  caisse (section 4). Aucun écart de solde, de transfert, d'écriture sans caisse,
  de net ou de remise. Ces chiffres ouvrent l'arbitrage de la direction
  (section 5) ; rien n'a été corrigé automatiquement.
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
  retrait de rôle. La validation/refus des demandes d'accès est partagée avec
  l'ADMIN (`access_request_review`), toujours limitée à `REQUESTABLE_ROLES`.
- Les actions SUPER_ADMIN ne sont pas affichées à un `ADMIN` (boutons
  « Créer un compte », « Modifier ») ; le formulaire d'approbation des
  demandes d'accès lui est en revanche affiché, avec le rôle suggéré
  présélectionné et modifiable.
- Tableau de bord ADMIN : indicateurs consolidés — étudiants actifs, demandes
  en attente, formateurs, formations actives, entrées et sorties du mois, solde
  total des caisses, reste à recouvrer des inscriptions en cours, détail des
  soldes par caisse — et panneau « Demandes d'accès en attente » avec le rôle
  suggéré de chaque demandeur.
- Techniquement : `ELEVATED_ROLES` / `User.is_elevated` ouvrent `role_required`
  et `permission_required` aux rôles `SUPER_ADMIN` et ADMIN ; le menu
  back-office est mutualisé dans `dashboard/admin/_nav.html` (Tableau de bord,
  Utilisateurs, Accueil & visites, Secrétariat, Étudiants, Pédagogie,
  Ressources, Groupes, Séances, Comptabilité, Journal, Caisses, Vue direction,
  Demandes d'accès, Bourses, Journal d'audit), le tableau de bord ADMIN regroupe
  des cartes d'accès direct aux modules et la topbar expose une icône
  « Pilotage » pour les deux rôles transversaux (`is_platform_admin`).

### Consultation seule des données métier (SUPER_ADMIN et ADMIN), la caisse exceptée
- Les deux rôles transversaux voient tout — visites, prospects, étudiants,
  inscriptions, séances, présences, transactions, reçus, ressources. La
  direction a demandé (arbitrage du 03/11/2026) qu'ils **tiennent aussi la
  caisse** : le reste du métier reste en consultation seule.
- Le décorateur `business_write_required` et des gardes explicites sur les vues
  mixtes renvoient un 403 côté serveur pour les écritures refusées : visite
  (création, départ, conversion), prospect (création, modification, relance),
  dossier étudiant et **création** d'inscription, motifs de visite, compte rendu
  de séance, feuille de présences, ressources, modules et leçons.
- Écritures ouvertes aux rôles élevés, chacune tracée dans l'audit :
  `cash_write_required` protège journal (opération, détail, annulation,
  correction), caisses (création, administration, ajustement, réinitialisation),
  clôtures et catégories ; `payment_write_required` laisse le super
  administrateur et l'ADMIN encaisser un paiement étudiant, le bouton
  « Encaisser » de la fiche inscription suivant la même règle. La création
  d'inscription au guichet (`can_enroll`) demeure une écriture de secrétariat.
- Exception assumée hors caisse : la **modification d'une inscription existante**
  (formation/session, statut, montant) est ouverte aux deux rôles élevés.
  La vue `enrollment_edit` est protégée par `role_required(*SECRETARIAT_ROLES)`
  — qui autorise `SUPER_ADMIN`/`ADMIN` en plus de `SECRETAIRE`/`DIRECTION` —
  et chaque modification est auditée (`ENROLLMENT_EDIT`). La création
  d'inscription et les autres écritures métier demeurent refusées.
- Écritures conservées : comptes utilisateurs, rôles, demandes d'accès et
  décision de bourse (réservée au SUPER_ADMIN ; l'ADMIN consulte le dossier
  avec une mention de lecture seule).
- L'interface masque les boutons et formulaires du métier fermé et affiche une
  mention de consultation ; la navigation et le rendu existants ne changent
  pas pour les rôles métier.
- Aucun formulaire affiché ne mène à un refus serveur : les contrôles visibles
  sont alignés sur les décorateurs des vues. Trois impasses ont été corrigées
  (le formulaire d'ajout de document de la fiche étudiant est masqué au
  `COMPTABLE`, qui consulte la fiche ; le bouton « Convertir en étudiant »
  d'une fiche prospect n'est plus proposé à l'`ACCUEIL`, la création de dossier
  étudiant restant au secrétariat ; le raccourci « Planifier une séance » de la
  liste des séances est réservé aux gestionnaires pédagogiques
  `FORMATEUR`/`RESP_PEDA`/`DIRECTION` et disparaît pour le secrétariat comme
  pour les rôles élevés). Audit de la couverture : aucune action de formulaire
  hors route, aucun POST sans `csrf_token`, aucune vue ciblée en GET only.
- Chaque fiche métier expose un historique d'audit « qui a fait quoi et
  quand » : étudiant, inscription, séance, visite, prospect, opération de
  caisse. Le journal global propose les mêmes liens vers ces fiches.

## 3. Couverture des tests

| Fichier | Tests | Périmètre |
|---|---:|---|
| `core/tests/test_public.py` | 16 | Landing, connexion locale (aucun widget externe), code interne, inscription avec rôle demandé, refus d'un rôle élevé, comptes en attente/suspendus, déconnexion |
| `core/tests/test_auth_roles.py` | 29 | Onboarding du rôle demandé, approbation/refus par SUPER_ADMIN et ADMIN (rôle suggéré présélectionné, modifiable ; rôles élevés refusés), étudiant validé automatiquement inscrit au groupe choisi (groupe obligatoire à la validation, jamais de doublon, apparu dans le formulaire de paiement), étudiant approuvé listé dans les inscrits côté comptable, auto-examen et auto-attribution bloqués, comptes suspendus exclus |
| `core/tests/test_profile.py` | 22 | Profil, avatar (upload, suppression, service protégé, fichier absent), mot de passe (nouveau valable et session conservée, mot de passe actuel incorrect ou vide, confirmation différente, mot de passe faible, audit sans le secret, compte sans mot de passe local), e-mail signé (succès, échec d'envoi, jeton invalide/expiré/autre compte, changement sans mot de passe local) |
| `core/tests/test_photo_profil.py` | 12 | Photo de profil : vignette partout (initiales sans photo, `<img>` et texte alternatif avec photo, liste des étudiants), pose par le secrétariat sur la fiche étudiant (dépôt + audit, aucun changement de statut, fichier remplacé effacé du disque, POST sans fichier laissant la photo en place, retrait, 403 pour un rôle non autorisé), pose par le super administrateur sur la fiche d'un autre compte et absence de la carte photo sur sa propre fiche |
| `core/tests/test_compteurs.py` | 5 | Compteurs communs : total des comptes, des étudiants et du staff, compte sans rôle compté seulement comme utilisateur, personne à double rôle présente dans les deux groupes, bande affichée sur les neuf tableaux de bord de rôle, aucune carte d'un gabarit ne reprend `total_users`, `total_students` ou `total_staff` |
| `core/tests/test_accueil.py` | 16 | Visites, contacts réutilisés, départ, conversion, prospects, relances, motifs, recherche ; « Convertir en étudiant » proposé au secrétariat et masqué à l'accueil |
| `core/tests/test_secretariat.py` | 15 | Étudiants, conversion prospect, inscriptions, remises, doublons, documents |
| `core/tests/test_pedagogie.py` | 58 | Modules/leçons (création et modification par formateur, resp. pédagogique et direction ; rôles élevés en lecture), groupes de formation (création/édition réservées au resp. pédagogique et à la direction, formateur et rôles élevés en lecture, périmètre limité aux groupes du formateur, validation des dates, audit), séances (raccourci « Planifier une séance » réservé aux rôles gestionnaires, masqué au secrétariat et aux rôles élevés), validations, présences, non-écrasement, ressources, accès étudiant, retour étudiant sur ressource (soumission, mise à jour sans doublon, validation, lecture par formateur/admin, refus formateur et rôles élevés en écriture), fiche de cours de l'apprenant (saisie, validation horaire, accès personnel), feuille de suivi imprimable et cahier de texte imprimable du formateur |
| `core/tests/test_comptabilite.py` | 111 | Journal, CSV, opérations, transferts, soldes, clôtures, paiements, reçu, permissions, liste des inscrits en consultation (nav, fiche en lecture, écritures et formulaire de document refusés), comptes étudiants sans inscription signalés sur l'écran d'encaissement, source unique des soldes et indicateurs, encaissement multi-mois et champ mois structuré, refus d'une recette datée après aujourd'hui, mois d'avance daté du jour présent, solde de caisse jamais négatif (sortie, transfert, annulation d'une entrée déjà dépensée, brouillon permis), administration des comptes (état, devise, découvert réservé au super admin, archivage, historique et audit, nom et ouverture figés après engagement), ajustement et réinitialisation traçables (écriture contraire, motif obligatoire, confirmation, brouillons signalés, rien d'effacé), catégories d'écriture administrables (création, renommage, compteur d'écritures, désactivation plutôt que suppression, Django Admin en consultation), correction d'une écriture enregistrée (montant, catégorie, libellé, date, motif ; écriture annulée fermée), disponible affiché et avertissement avant sortie (80 % du disponible, case à cocher, recette et brouillon dispensés, « Solde épuisé » et « Aucun fonds disponible ») |
| `core/tests/test_permissions.py` | 50 | Routage des dashboards, accès croisés, super admin, compte sans rôle, accès transversal de l'ADMIN, lecture seule des deux rôles transversaux sur le métier sauf la caisse (journal, encaissement, clôture, comptes, catégories ouverts en écriture et audités ; exception : édition d'inscription ouverte aux rôles élevés), décision de bourse réservée au SUPER_ADMIN (notification interne, e-mail, panne SMTP, statut forgé rejeté, chemin Django Admin), historiques par fiche et liens du journal d'audit, rôle Assistant administratif et retrait d'Accueil/Caisse de ses menus |
| `core/tests/test_supervision.py` | 10 | Supervision financière (accès, exhaustivité, filtres, totaux, export CSV), indicateurs réels du dashboard super admin, calcul du reste à recouvrer dossier par dossier, historique de transaction, filtres et rendu du journal d'audit |
| `core/tests/test_admin_access.py` | 9 | Accès transversal de l'ADMIN : ouverture de tous les modules, reçu de paiement, document étudiant, catalogue de ressources, revue des demandes d'accès ; refus (403) sur création/édition de comptes et attribution de rôles |
| `core/tests/test_audit_finances.py` | 4 | Rapport de cohérence financière : base saine, trop-perçu signalé, paiement sans mouvement de caisse, écriture de caisse ou paiement datés après aujourd'hui |
| `core/tests/test_user_access.py` | 30 | Fiche utilisateur : présence/absence des contrôles selon le rôle et la cible, ajout/retrait de rôle, génération automatique du code interne à l'attribution, avertissement quand un compte étudiant reste sans inscription (attribution de rôle, édition du compte, réactivation par changement de statut — un étudiant déjà inscrit ne reçoit pas l'avertissement), rôle et action inconnus, auto-modification bloquée, changement de statut (suspension, réactivation, `disabled_at`, perte d'accès), statut invalide, absence d'audit sans changement, garde-fou du dernier super administrateur actif, compte étudiant créé directement inscrit au groupe choisi (groupe exigé, créé sinon) |
| `core/tests/test_statut_etudiant.py` | 12 | Statut par défaut d'un étudiant, approbation à la validation de l'inscription, comptes sortis des classeurs, `mettre_en_attente` en aperçu puis à l'écriture, aucune révocabilité automatique |
| `core/tests/test_import_eleves.py` | 37 | Vague 2 : ce que le classeur d'élèves devient en base et ce qui ne le devient pas (comptes, groupes, inscriptions, paiements, doublons ignorés et signalés, aucune retouche d'un tarif payé, case de mois d'un mois non encore commencé signalée sans encaissement) |
| `core/tests/test_feuille_import.py` | 19 | Rapprochement du journal de caisse « Contrôles Mensuels » avec les écritures de la base (différentiel en lecture seule, écritures manquantes, écarts de montant, solde projeté de la caisse avant écriture du lot, instant d'écriture jamais postérieur au jour de l'import) |
| `core/tests/test_dates_caisse.py` | 6 | Dates de caisse : aperçu qui ne modifie rien, correction d'un paiement et de son écriture au jour de saisie, mois réglé conservé, trace d'audit `PAYMENT_DATE_FIX`, écriture sans paiement corrigée et auditée, seconde passe sans effet |
| `core/tests/test_importer_formations.py` | 15 | Tarif lu dans les classeurs et portique de la vague 1 (catalogue des formations, mensualités, aucune écriture en base) |
| `core/tests/test_data_tools.py` | 9 | Lecteurs de classeurs : ce sont eux qui décident de ce qui sera importé (en-têtes, dates, montants, lignes vides) |
| `core/tests/test_editeur_permissions.py` | 10 | Éditeur de permissions du super admin : la matrice postes × droits et son effet réel à l'écran (un droit coché ouvre l'écran, décoché le ferme) |
| `core/tests/test_graphiques.py` | 19 | Séries numériques des graphiques de tableau de bord (bornes de période, buckets mensuels, totaux cachés derrière une courbe) |
| `core/tests/test_i18n_theme.py` | 18 | Coquille bilingue : la langue choisie est suivie, le thème reste neutre, les notifications s'empilent hors du fil de la page, les variables des msgid ne sont pas renommées dans le catalogue anglais |
| `core/tests/test_annee_academique.py` | 40 | Année académique : garde du modèle (une seule « en cours », fenêtre incohérente, libellé unique), service de résolution et de filtrage (groupes, inscrits, étudiants, compte sans inscription), écran des années (création, réglage, bandeau, rôles refusés, Django Admin en consultation), les quatre écrans filtrés et le contrôle de non-mélange du calendrier |
| `core/tests/test_sans_melange.py` | 8 | Aucun mélange de langue au rendu, page par page (complément du portique `verifier_i18n`), calendrier, sélecteur d'année et paramètres généraux inclus ; tous les gabarits du projet se compilent et aucun `{% blocktrans %}` ne garde une variable à points (qui rend vide sans erreur) |
| `core/tests/test_parametres.py` | 19 | Paramètres généraux : ligne née avec la migration et seconde ligne refusée en base, service qui ne crée jamais la ligne, bloc légal filtrant les vides, nom obligatoire ; seuil hors bornes refusé puis lu par l'avertissement de caisse (60 % annoncé, 90 % muet) et devise nommée dans l'alerte ; écran (formulaire, POST audité avec son avant, seuil absurde refusé sans écriture, 403 du secrétariat, historique affiché) ; affichage (nom sur les tableaux de bord, `<meta name="devise">` et devise dans le journal, coordonnées sur l'accueil public, reçu portant nom, RCCM et téléphone) ; Django Admin en consultation seule sur les tables financières, la caisse et les réglages |
| `core/tests/test_relations.py` | 34 | Cohérence des relations entre tables : base saine muette sur les 16 contrôles et preuve que mesurer n'écrit rien ; chaque écart semé est nommé par son code (recette d'étudiant sans paiement, recette d'une autre catégorie hors jeu, paiement sans écriture, paiement en attente déjà en caisse, transfert sans destination, net incohérent, remise démesurée, trop-perçu, dossier double, dossier terminé non compté double, date future, mensualité sans mois, solde sous le découvert autorisé et découvert accordé, compte actif sans dossier, présence orpheline) ; signalements du journal (entité disparue, clé de format inconnu, réglage d'écran) et des groupes à combler (nommés avec leurs inscrits, terminés ignorés, effacés par l'affectation) ; portique de la commande (passe, refuse en nommant le code fautif, seuil accepté, `--code` isolé, `--json` sur une ligne, `--lignes` borné) et indifférence aux réglages posés |
| **Total** | **695** | Exécuté le 20/11/2026, `python manage.py test core.tests`, 0 échec |

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
- SUPER_ADMIN et ADMIN : refus (403) sur les écritures métier hors caisse (GET des
  formulaires et POST des vues mixtes) et données inchangées après tentative ;
  actions correspondantes absentes des écrans. La caisse leur est ouverte en
  écriture (opération, annulation, correction, paiement, clôture, compte,
  catégorie) et chaque geste laisse sa ligne d'audit ;
- solde de caisse : un ajustement, une réinitialisation, une correction
  d'écriture ou une sortie qui consomme plus que le disponible sont refusés avec
  le montant manquant, et la garde s'applique aussi au `save()` du modèle — un
  script qui écrirait directement ne creuse pas la caisse ;
- avertissement avant sortie : le disponible se lit sur l'écran de saisie et
  dans le choix de la caisse, une sortie à 80 % et plus du disponible est
  annoncée avec son pourcentage et bloquée tant que la case n'est pas cochée,
  une recette et un brouillon n'ont rien à confirmer ;
- comptes financiers : l'archivage ferme le compte aux écritures et le retire
  des listes, le découvert reste à 0 tant qu'un super administrateur ne le fixe
  pas, nom et solde d'ouverture ne se rejouent pas une fois la caisse engagée ;
- catégories : une catégorie utilisée se désactive, ne se supprime pas, et le
  compteur d'écritures empêche le renommage aveugle ;
- Django Admin financier : les quatre modèles sont lisibles (listes, filtres,
  recherche, solde calculé, hiérarchie par date) et l'écriture y est refusée —
  la caisse ne se tient que depuis le tableau de bord ;
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
- authentification : un compte en attente est bloqué et redirigé vers la
  complétion de son rôle demandé ;
- inscription : le rôle demandé est enregistré sans être attribué ; une
  demande de rôle élevé (SUPER_ADMIN/ADMIN) est refusée ;
- approbation : le formulaire ne propose pas SUPER_ADMIN/ADMIN, présélectionne
  le rôle demandé ; l'approbation attribue
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
- Inscription : aucun rôle demandé n'était recueilli ; le compte
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
- Photo de profil : elle n'apparaissait que sur « Mon profil ». Une balise
  `{% vignette %}` unique l'affiche désormais sur les listes et les en-têtes des
  écrans fréquentés, avec repli sur les initiales ; le secrétariat et le super
  administrateur peuvent la poser pour un compte qui ne se connecte pas ; le
  fichier remplacé est supprimé du disque et la pose est auditée avec son
  auteur.
- Nouvelle commande `manage.py audit_finances` (lecture seule) : trop-perçus,
  paiements sans mouvement de caisse, montants divergents, soldes négatifs.
- Nouvelle commande `manage.py verifier_relations` : les seize relations promises
  par les modèles sont mesurées en lecture seule et servent de portique (voir
  section 2).
- Reçu et documents imprimés **sans coordonnées** : quatre gabarits appelaient
  `plateforme.contacts` alors que `PlatformSetting` n'avait pas cette méthode —
  Django rend vide au lieu de se plaindre. La méthode est écrite sur le modèle
  (les lignes vides sont filtrées) et le service `core.parametres.contacts()`
  lui délègue, pour qu'une seule règle serve l'écran et l'impression.
- Audit des réglages **sans état d'avant** : `BaseModelForm.is_valid()` écrit déjà
  les nouvelles valeurs sur l'instance ; relevé après la validation, le `before`
  de l'audit était identique à l'`after`. Il se relève désormais avant la
  construction du formulaire.
- Extraction i18n **qui avalait des gabarits** : le motif de recherche ne
  reconnaissait pas `{% endblocktranslate %}` et cherchait la fermeture
  `endblocktrans` plus loin, produisant un msgid géant et faisant disparaître le
  vrai. Les deux orthographes sont admises à l'ouverture comme à la fermeture.
- Titre de la fiche de cours de l'étudiant **amputé du nom** :
  `{% blocktrans %}… {{ plateforme.nom }}{% endblocktrans %}` — Django rend une
  variable à points vide dans un `blocktrans`, sans erreur ni compilation
  refusée. Passage à `with n=plateforme.nom`, et la garde de rendu refuse
  désormais toute variable non résolue dans un msgid.
- « FCFA » en dur : dix-neuf lignes de gabarits, les deux libellés du JavaScript
  des graphiques (qui lit maintenant `<meta name="devise">`) et les labels,
  aide et messages Python portent la devise lue dans les réglages ; le portique
  balaie `core/parametres.py` comme les autres services qui écrivent des mots
  donnés à voir.
- Listes filtrées : cinq index composites (`0018_index_listes_filtrees`) posés
  sur la date de début des groupes, le statut des dossiers, les paiements validés
  par date, le journal par entité et les écritures par compte.
- Django Admin : `Payment`, `Enrollment`, `Attendance`, `Expense`, `Certificate`
  et `PlatformSetting` passent en `ConsultationSeule` (addition, modification et
  suppression refusées) ; la consultation des écritures reste le comportement
  Django.
- Dates de caisse **dans l'avenir** : l'import du journal recopiait le mois
  pré-rempli du classeur (mensualités datées de décembre 2026 à avril 2027 alors
  que l'argent était reçu en novembre). L'instant d'écriture passe désormais par
  `core.feuille_import.instant_de()`, qui ramène toute ligne au jour de l'import
  à midi sans toucher au mois réglé (`period_year` / `period_month`) ; la
  commande signale les lignes concernées. Les douze lignes déjà fautives ont été
  corrigées par `manage.py regulariser_dates_caisse --ecrire` (aperçu par défaut,
  audits `PAYMENT_DATE_FIX` / `CASH_DATE_FIX`, réexécutable sans effet).

## 5. Éléments volontairement non couverts / restants

Ces points ne sont pas déclarés terminés :

- **Photos de profil non redimensionnées** : le fichier déposé est enregistré
  tel quel. Les photos déjà en base pèsent de 2 à 8 Mo (jusqu'à 3840 × 2160) et
  sont servies entières dans une vignette de 36 px ; une liste de vingt
  étudiants peut donc transférer plusieurs dizaines de mégaoctets. Un
  redimensionnement à la pose (ou une vignette pré-calculée) reste à décider.
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
  `etudiant@univers.academy` / « Les langues étrangères » (ex-« Anglais B2 »,
  net 75 000 FCFA) porte quatre
  paiements validés pour 135 000 FCFA, soit 60 000 FCFA de trop-perçu. Le
  formulaire actuel refuse un montant supérieur au reste à payer ; ces
  encaissements proviennent d'une saisie antérieure au garde-fou. Aucune
  correction automatique n'a été faite : à régulariser manuellement
  (remboursement ou annulation tracée). `manage.py audit_finances` le signale.
- **Cohérence mesurée le 06/11/2026, à arbitrer par la direction** :
  `manage.py verifier_relations` rend **177 écarts et 39 signalements** sur la
  base réelle, tous antérieurs aux garde-fous aujourd'hui posés, et **rien n'a
  été corrigé automatiquement** (règle : rien ne se supprime ni ne s'écrit sans
  accord).
  158 recettes classées « Paiements des étudiants » sans paiement d'étudiant
  correspondant (2 986 000 FCFA — l'import du journal de caisse encaissait sans
  remplir un dossier) ; 8 dossiers doubles (même étudiant, même formation, deux
  inscriptions actives) ;
  3 trop-perçus (le pire, `UA-ETU-0116`, à +250 000 FCFA) ; 2 mensualités réglées
  sans mois soldé ; 6 comptes étudiants actifs sans aucun dossier. Les douze
  écritures datées après aujourd'hui relevées le 05/11 ont depuis été ramenées au
  jour de saisie par `manage.py regulariser_dates_caisse --ecrire` (section 4) :
  le contrôle est muet au 06/11. S'y ajoutent 39
  **signalements** comptés à part et non bloquants : 30 lignes du journal
  d'audit citant une entité disparue (traces légitimes d'une suppression) et 9
  groupes sans formateur, qui portent 70 dossiers d'inscription actifs.
- **Solde de caisse négatif constaté le 01/11/2026, régularisé le 04/11/2026** :
  la caisse « Mobile Money » affichait un creux car deux sorties « mois
  d'octobre » du 30/10/2026 (100 000 et 100 FCFA) y avaient été enregistrées
  alors que le portefeuille ne contenait aucune recette. Cause analysée avant
  correction : ce ne sont pas les dépenses qui étaient fausses, c'est leur
  imputation — et l'affichage ne cachait aucun bug. Arbitrage de la direction
  (« ressaisir sur la Caisse principale ») : les deux sorties restent dans le
  journal, annulées et motivées, et sont reportées sur la caisse qui a payé
  (`TRX-2026-1014`, `TRX-2026-1015`). La caisse solde aujourd'hui à +50 000
  FCFA, montant d'une recette étudiante réellement encaissée en Mobile Money.
  `manage.py
  audit_finances` ne signale plus aucun solde négatif, et le plancher de solde
  rendu infranchissable rend ce creux impossible à reproduire.
- **Sécurité de déploiement** : le `.env` de développement laisse `DEBUG=True`,
  `SECRET_KEY` ne fait que 23 caractères et `SECURE_HSTS_SECONDS` n'est pas
  défini. Les comptes de démonstration (`admin@univers.academy`, superuser,
  `secretaire@…`, `comptable@…`, etc.) ont encore leurs mots de passe par
  défaut actifs : à désactiver ou renouveler avant toute exposition publique.

## 6. Livrable documentaire

Le document d'architecture métier est généré par script afin de rester aligné
sur le code :

```powershell
env\Scripts\python.exe docs\generate_architecture_docx.py
```

- Fichier produit : `docs/Architecture_metier_Univers_Academy.docx`.
- Générateur : `docs/generate_architecture_docx.py` (`python-docx` 1.2.0).
- Contenu : 14 chapitres et 6 annexes, 125 tableaux, 108 règles de gestion,
  37 modèles décrits champ par champ, 112 routes nommées, 69 actions d'audit.
- Les tableaux des annexes B (routes) et D (modèles) sont introspectés depuis
  Django à chaque génération ; le catalogue d'audit a été confronté aux appels
  `log_audit` du code (69 codes dans le document, 69 dans le code : 62 appels
  directs et 7 codes acheminés par `_tracer` ou par une expression conditionnelle).
- Contrôles effectués sur le fichier généré : aucun champ « None », titres
  d'annexes non redondants, dates et compteurs de tests cohérents avec la
  présente validation.
- Contrôle HTTP en lecture (formateur, étudiant, ADMIN, SUPER_ADMIN) : cahier
  de texte, impression, fiches de cours, feuille de suivi, demandes d'accès,
  utilisateurs, journal d'audit et supervision répondent en 200 ; l'étudiant
  reçoit 403 sur le cahier de texte, l'ADMIN 403 sur les écritures du cahier de
  texte, et un visiteur anonyme est redirigé vers la connexion.
