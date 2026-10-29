# Authentification Clerk — Google / Gmail et email + mot de passe

L'application utilise **Clerk** comme fournisseur d'identité principal, tout en
conservant la connexion interne (email + mot de passe Django) comme solution de
repli pour les comptes existants.

## 1. Créer l'application Clerk

1. Créer un compte sur <https://dashboard.clerk.com> puis une application.
2. Dans **API keys**, récupérer :
   - la **Publishable key** (`pk_test_...` ou `pk_live_...`) ;
   - la **Secret key** (`sk_test_...` ou `sk_live_...`).

## 2. Configurer `.env`

```dotenv
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
# Facultatif : déduit automatiquement de la publishable key
CLERK_FRONTEND_API=nom-de-l-app.clerk.accounts.dev
# Origines autorisées à utiliser la session Clerk (azp du JWT)
CLERK_AUTHORIZED_PARTIES=http://localhost:8000,http://127.0.0.1:8000
```

Sans ces deux clés, `CLERK_ENABLED` reste à `False` : la page de connexion
affiche uniquement le formulaire classique, rien ne casse.

## 3. Activer Google et le mot de passe dans Clerk

Dans le dashboard Clerk :

- **User & Authentication → Email, phone, username**
  - activer **Email address** ;
  - activer **Password** (sinon Clerk utilise un code par email) ;
  - activer la vérification de l'email.
- **User & Authentication → Social connections**
  - activer **Google**.
  - En développement, les identifiants Google partagés de Clerk suffisent.
  - En production, créer un client OAuth dans Google Cloud Console
    (type *Web application*) et renseigner l'URI de redirection affichée par
    Clerk : `https://<votre-frontend-api>/v1/oauth_callback`.

Les comptes **Gmail** fonctionnent via la connexion Google : aucun réglage
supplémentaire côté Django.

## 4. Appliquer côté Django

```powershell
D:\Dev\01_Professionnel\Django\univers-academie\env\Scripts\python.exe -m pip install -r requirements.txt
D:\Dev\01_Professionnel\Django\univers-academie\env\Scripts\python.exe manage.py migrate
```

Puis redémarrer le serveur. La page `/login/` affiche le composant Clerk
(Google + email/mot de passe) et, en dessous, la connexion interne.

## 5. Fonctionnement

1. Clerk authentifie l'utilisateur dans le navigateur (Google OAuth ou
   email/mot de passe) et crée une session Clerk.
2. Le JavaScript récupère le **session token** et le poste, avec le jeton CSRF,
   sur `POST /clerk/session/`.
3. Django vérifie la signature, l'expiration, l'émetteur et l'`azp` du JWT avec
   `clerk-backend-api`, puis récupère le profil via l'API Clerk.
4. Le compte local est retrouvé :
   - par `clerk_user_id` s'il est déjà lié ;
   - sinon par email (insensible à la casse), puis lié automatiquement — à
     condition que Clerk confirme que l'adresse est **vérifiée** (protection
     contre l'usurpation de compte) ;
   - sinon un compte `PENDING_APPROVAL` est créé, **sans aucun rôle**. Les
     métadonnées publiques de Clerk (`public_metadata`, `unsafe_metadata`,
     `role`, etc.) ne sont jamais lues comme source d'autorité.
5. Si l'utilisateur n'a pas encore indiqué de rôle demandé, il est redirigé
   vers `/demande-acces/` pour compléter son identité et choisir un **rôle
   demandé** (étudiant, formateur, secrétaire, comptable, responsable
   pédagogique, accueil). Ce rôle est enregistré dans `AccessRequest`, jamais
   dans `UserRole` : il ne donne aucun droit.
6. Django ouvre sa propre session : le reste de l'application (rôles,
   tableaux de bord, audit) continue de fonctionner sans modification.

La déconnexion ferme la session Django **et** la session Clerk, afin d'éviter
une reconnexion silencieuse.

## 6. Approbation et attribution du rôle effectif

- Un compte `PENDING_APPROVAL` reste bloqué par `AccountStatusMiddleware` :
  `/dashboard/...` redirige vers la page d'attente, aucun écran métier n'est
  accessible.
- Seul un **SUPER_ADMIN** (et non un ADMIN) peut approuver, refuser, suspendre
  ou révoquer depuis `/dashboard/super-admin/access-requests/`
  (`super_admin_required`).
- À l'approbation, le SUPER_ADMIN choisit le rôle effectif. Le serveur
  n'accepte que `REQUESTABLE_ROLES` (étudiant, formateur, secrétaire,
  comptable, responsable pédagogique, accueil) : `SUPER_ADMIN`, `ADMIN` et
  `DIRECTION` sont refusés même si la valeur est postée à la main. Un rôle
  élevé s'attribue ensuite, séparément, depuis la fiche utilisateur.
- L'approbation écrit `assigned_role` sur la demande, passe le compte en
  `ACTIVE`, génère le code interne et envoie la notification. Le journal
  d'audit conserve : demandeur, rôle demandé, rôle attribué, statut avant/après,
  décideur, horodatage et note de décision.
- Un utilisateur ne peut ni examiner sa propre demande (403), ni modifier son
  propre rôle, ni changer son rôle/statut via le POST du profil.
- Le rôle demandé n'est jamais considéré comme effectif ; les contrôles
  d'accès lisent uniquement `UserRole` en base.

## 7. Initialisation sécurisée du SUPER_ADMIN

Aucun compte ne devient SUPER_ADMIN par inscription, par Clerk ou par défaut.
Le premier super administrateur se crée avec une commande contrôlée :

```powershell
$env:SUPERADMIN_SETUP_SECRET = '<secret-long-et-unique>'
$env:SUPERADMIN_EMAIL = 'vous@exemple.com'
$env:SUPERADMIN_PASSWORD = '<mot-de-passe-fort>'
.\env\Scripts\python.exe manage.py create_superadmin
```

La commande refuse de s'exécuter sans secret, crée un compte `ACTIVE`,
`is_superuser=True`, avec le rôle `SUPER_ADMIN`, et n'écrit aucun mot de passe
dans le journal d'audit. Ensuite, `manage.py audit_privileges` (lecture seule)
signale les combinaisons à vérifier (SUPER_ADMIN lié à Clerk, compte non actif
avec rôle élevé, rôle élevé sans `is_superuser`, etc.) sans rien modifier.

## 8. Production

- Passer les clés `pk_live_...` / `sk_live_...`.
- Renseigner le domaine réel, par exemple :
  `CLERK_AUTHORIZED_PARTIES=https://academy.mondomaine.com`.
- Ajouter ce domaine à `CSRF_TRUSTED_ORIGINS` dans
  `univers_academy/settings.py`.
- Servir le site en HTTPS (`DEBUG=False` active déjà les cookies sécurisés).
