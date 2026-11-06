# Sécurité — ProfileLink

État au 2026-11-06. Le détail des choix est dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Rôles

| Rôle | Accès |
|---|---|
| Administrateur | Compte créé en ligne de commande, ou par une route FastAPI protégée par un code. Seul à gérer les VA. |
| Visiteur | Aucun compte. Pages publiques et redirection, sans droit de modification. |
| VA | Aucun compte, mot de passe, session ni accès. |

Aucune route ne crée de compte sans le code `REGISTRATION_TOKEN`. Tout compte étant administrateur, ce code donne le contrôle de tous les VA : **laissez-le vide hors création de compte**, la page répond alors 404.

## Mesures en place

### Authentification

- Mots de passe en Argon2id, de 12 à 128 caractères.
- Session opaque de 256 bits : seul son SHA-256 est stocké, et la révocation est immédiate.
- Cookie `HttpOnly`, `Secure`, `SameSite=Lax`, valable 14 jours.
- Une connexion ratée ne révèle pas si le compte existe.
- `SameSite=Lax` + contrôle d'`Origin` sur toute écriture de `/auth/*` et `/admin/*`, en remplacement d'un jeton CSRF. Seuls le site et la même origine que l'API sont acceptés.
- Toutes les routes `/admin/*` sont protégées au niveau du routeur.
- `proxy.ts` valide la session auprès de FastAPI avant de servir le dashboard : un faux cookie n'obtient même pas la page.
- `POST /api/v1/auth/register` et `/register` : absentes du frontend, désactivées sans code, code de 32 caractères minimum comparé en temps constant, limite stricte de Nginx, aucune session ouverte.

### Destinations

- Stockées uniquement dans PostgreSQL. Absentes du JSON public, du HTML, des métadonnées et du JavaScript, ce que les tests vérifient.
- Lues au clic par FastAPI, qui répond `302` avec `Cache-Control: no-store`. Aucun paramètre de requête ne peut les influencer.
- Validées à l'enregistrement : `http` ou `https` uniquement, pas d'identifiants, pas de nom local, pas d'IP privée ou réservée sous toutes leurs formes, pas de boucle vers le service.
- L'API ne contacte jamais une destination : il n'y a pas de surface SSRF à l'exécution.

**La destination devient visible dans l'en-tête `Location` au moment du clic.** Elle n'est pas secrète après coup, et le produit ne prétend pas le contraire.

### Données

- Adresses IP jamais stockées : HMAC-SHA256 avec une clé secrète.
- Cookie `pl_visitor` : aléatoire, `HttpOnly`, un an, posé uniquement au clic, stocké haché. Il sert à ne compter un clic qu'une fois, ce que `/conditions` indique.
- Aucun identifiant interne dans les réponses publiques ni dans les URL du dashboard.
- Photos décodées puis réencodées : métadonnées et GPS supprimés, fichiers déguisés refusés, 5 Mo au maximum.
- Requêtes SQL paramétrées, paramètres absents des journaux.
- Journaux JSON sans destination, ni IP, ni mot de passe.

### Pages publiques

- Même réponse pour tous les User-Agents : aucun cloaking.
- `noindex, nofollow` sur chaque page, âge absent d'Open Graph.
- Lien Instagram réservé au dashboard : aucune réponse publique ne le contient, ce que les tests vérifient.
- Un VA désactivé n'expose plus aucune donnée personnelle.

### En-têtes et réseau

- CSP, `nosniff`, `Referrer-Policy`, HSTS, `frame-ancestors 'none'`.
- CSP avec `script-src 'unsafe-inline'` : Next l'exige sans nonces, et des nonces imposeraient un rendu à chaque requête. C'est le point faible connu de la politique.
- CORS limité à l'origine du site.
- `/backend` est une liste blanche : `/docs`, `/health` et l'inscription ne sont pas accessibles par le site.
- Rate limiting Nginx, par IP réelle du visiteur.
- PostgreSQL sur un réseau Docker interne, sans port publié.
- Origine réservée à Cloudflare par certificat client. Un filtrage UFW ne suffirait pas : les ports publiés par Docker le contournent.
- `/api/revalidate` bloquée sur Internet par Nginx, et protégée par un secret.

## Limites connues

- Pas de double authentification.
- Pas de journal d'audit des actions de l'administrateur.
- Aucun âge minimum n'est imposé : la publication d'un mineur reste possible.
- Pas de durée de conservation automatique pour `ip_hash` et `user_agent`.
- Les statistiques peuvent être faussées : le beacon de visite est public, et une requête fabriquée à la main peut falsifier son IP (`X-Real-IP`), y compris à travers Vercel. Un navigateur normal ne le peut pas.
- Le port 2560 du VPS reste joignable directement, sans passer par Vercel ni par ces protections de routes. FastAPI y vérifie quand même chaque appel.

## À faire avant la mise en ligne

- [ ] Consentement écrit de chaque VA pour la publication de ses données.
- [ ] Revue juridique de `/conditions`.
- [ ] Création effective de `abuse@profil.mg`.
- [ ] Secrets de production générés et conservés hors du dépôt.
- [ ] Mot de passe administrateur long, enregistré dans un gestionnaire.
- [ ] `REGISTRATION_TOKEN` vide une fois les comptes créés.
- [ ] Copie des sauvegardes hors du VPS.

Signaler une faille : `abuse@profil.mg`.
