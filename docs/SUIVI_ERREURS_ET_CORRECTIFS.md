# Suivi des erreurs et correctifs — Système de Gestion de Stock

> مرجع لتتبع أخطاء التطبيق وإصلاحاتها. يُحدَّث عند كل تدخل.
> Référence de suivi des erreurs et correctifs. Mettre à jour à chaque intervention.

---

## 1. Informations générales

| Élément | Valeur |
|---|---|
| Projet local | `D:\Users\DT01\Desktop\stock2\projet_stock` |
| Serveur de production | `/home/bazighe82/Engor/mysite/` (PythonAnywhere, compte **gratuit**) |
| GitHub | `https://github.com/cima4you/-projet-stock.git` (branche `main`) |
| Base de données | SQLite `stock.db` (20 produits, 57 mouvements au 04-08-2026) |
| SMTP | `smtp.gmail.com:587` — expéditeur `bazigherachid@gmail.com` |
| CRON_SECRET (serveur) | défini dans `.env` du serveur (différent du local) |
| Déclencheur rapport quotidien | cron-job.org, job « Rapport quotidien stock », **19:00** tz `Africa/Casablanca`, URL `/cron/daily-report?token=<CRON_SECRET>` |

---

## 2. Flux principaux (عمل التطبيق)

### Authentification
1. `routes/auth.py` : login → stocke `workshop_id` + `workshop_name` dans la session.
2. Toutes les routes de données utilisent `workshop_filter()` de `utils.py` pour filtrer par atelier.
3. Rôles : `user`, `admin`, `principal_admin`. Admin par défaut : défini via `DEFAULT_ADMIN_USERNAME`/`DEFAULT_ADMIN_PASSWORD` dans `.env` (à changer après la première connexion).

### Produits & mouvements
- `routes/products.py` : ajout/modification produit → insère aussi un `stock_movements` (entry/exit).
- `routes/movements.py` : mouvements avec types `entry`, `exit`, `transfert`.
- Table : `stock_movements` (pas `movements` !).

### Notifications d'ajout produit
- `notifications.py` `send_product_addition_notification()` : envoie un email (français) aux destinataires de l'atelier.
- Destinataires dans `notification_recipients` + `recipient_emails` (gestion via `/email_management`).

### Rapport quotidien
1. **cron-job.org** appelle à 19:00 : `/cron/daily-report?token=...` → `routes/cron.py`.
2. `notifications.py:535` `send_daily_report_if_not_sent()` :
   - Vérifie `notification_logs` : si une ligne `daily_report` existe pour `DATE(sent_at)=date('now')` → **skip** (Already sent today).
   - Sinon génère 4 pièces jointes (rapport_produits.xlsx/pdf + rapport_mouvements.xlsx/pdf) et les envoie à **chacun** des `DAILY_REPORT_RECIPIENTS`.
3. Chaque destinataire reçoit SA propre copie dans SON boîte mail (pas de copie visible chez l'expéditeur).

---

## 3. Destinataires du rapport quotidien

- **Définition** : `config.py:70` `DAILY_REPORT_RECIPIENTS` lu depuis la variable d'env `.env` (`DAILY_REPORT_RECIPIENTS`, séparée par virgules).
- **IMPORTANT** : `config.py` est chargé **une seule fois au démarrage**. Après modification de `.env` → **Reload** obligatoire.
- **Liste actuelle (6)** :
  1. bazigherachid@gmail.com
  2. rbazighe@gmail.com
  3. hmiddouchhamza@gmail.com
  4. younesghazzali1995@gmail.com
  5. mohammed.chabli@engor.net
  6. yassinenaitoufqir@gmail.com

---

## 4. Table `notification_logs` — schéma & requêtes utiles

Schéma (`db.py:280`) :
```sql
notification_logs(id, recipient_email, notification_type, subject, content, product_id, sent_at, status)
```
`status` : `'sent'` | `'failed'`.

Requêtes de diagnostic (Bash console PythonAnywhere) :

```bash
# Derniers envois du rapport quotidien
cd ~/Engor/mysite && python3 -c "import sqlite3;c=sqlite3.connect('stock.db');print(c.execute(\"SELECT recipient_email,status,sent_at FROM notification_logs WHERE notification_type='daily_report' ORDER BY id DESC LIMIT 5\").fetchall())"

# Comptage produits / mouvements (vérification d'intégrité)
python3 -c "import sqlite3;c=sqlite3.connect('stock.db');print('products:',c.execute('SELECT COUNT(*) FROM products').fetchone()[0]);print('movements:',c.execute('SELECT COUNT(*) FROM stock_movements').fetchone()[0])"

# Liste des destinataires lus par config
python3 -c "from config import DAILY_REPORT_RECIPIENTS; print(DAILY_REPORT_RECIPIENTS)"

# ⚠️ TEST SEULEMENT — réinitialiser l'envoi du jour (provoque un renvoi immédiat)
python3 -c "import sqlite3;c=sqlite3.connect('stock.db');c.execute(\"DELETE FROM notification_logs WHERE notification_type='daily_report' AND DATE(sent_at)=date('now')\");c.commit();print('cleared')"

# Déclencher l'envoi (après reset) — même URL que cron-job.org
curl -s "https://bazighe82.pythonanywhere.com/cron/daily-report?token=$CRON_SECRET"
```

**Règles d'or** :
- ❌ Ne JAMAIS effacer `notification_logs` sauf en cas de test (sinon renvoi multiple).
- ✅ Après modification de `.env` → **Reload** web obligatoire (sinon ancienne config).
- ✅ Backup `stock.db` avant toute manipulation.

---

## 5. Erreurs et correctifs (historique)

| # | Erreur | Fichier:Ligne | Cause | Correctif | Statut |
|---|---|---|---|---|---|
| 1 | Rapport quotidien envoyé à 4 destinataires seulement, `mohammed.chabli@engor.net` manquant | `config.py:70` + `.env` | `config.py` lit `.env` au démarrage ; process WSGI longévif gardait l'ancienne liste (ou variable d'env forcée dans Web tab) | Vérifier `.env`, **Reload** web, confirmer avec le check config | ✅ RÉSOLU 04-08-2026 |
| 2 | `'float' object has no attribute 'strip'` (échec notifications d'ajout produit) | `notifications.py:183` et `:287` | Numéros BC/BL/Facture importés d'Excel arrivent en `float` ; `.strip()` échoue | `str(product_info.get(key, '')).strip()` | ✅ RÉSOLU 04-08-2026 |
| 3 | `database is locked` (récurrent) | `db.py:139` | Concurrence SQLite sans timeout | `sqlite3.connect(DB_PATH, timeout=30)` | ✅ RÉSOLU 04-08-2026 |
| 4 | `'sqlite3.Row' object has no attribute '_emails'` | `routes/email_mgmt.py` (ancien) | Ancienne version du code | Code actuel utilise `r[0]`, `r[1]`… + `'placeholder@local'` | ✅ Déjà corrigé — ne pas refaire |
| 5 | `NOT NULL constraint failed: notification_recipients.email` | `routes/email_mgmt.py:97` | Champ `email` requis dans la table | `INSERT` avec `'placeholder@local'` | ✅ Déjà corrigé — ne pas refaire |
| 6 | `ModuleNotFoundError: No module named 'flask_moment'` | environn. | Dépendance absente | `pip install flask_moment` | ✅ Historique |
| 7 | `ImportError: cannot import name 'app' from 'flask_app'` | import | Chemin d'import erroné | Import corrigé | ✅ Historique |
| 8 | **Nouvelle règle** : seul l'admin peut modifier/corriger un produit | `routes/products.py:186` + `templates/products.html:227` | Tout utilisateur connecté pouvait modifier (`@login_required`) | `@admin_required` sur `edit_product` + bouton modif caché aux non-admins | ✅ RÉSOLU 04-08-2026 (`e21ec64`) |
| 9 | **Nouvelle règle** : édition + suppression de mouvement réservées aux admins (avec recalcul du stock) | `routes/movements.py` (`edit_movement`, `delete_movement`) + `templates/movements.html` + `templates/edit_movement.html` (nouveau) | Aucune édition/suppression de mouvement n'existait | Routes `@admin_required` + boutons admin-only + recalcul automatique de la quantité produit (gardes anti-stock négatif) | ✅ Ajouté 04-08-2026 |
| 10 | **Nouvelle fonctionnalité** : journal de suivi complet (entrées/sorties + qui a fait quoi) | `routes/auth.py` (login/login_failed/logout), `db.py` (table `login_logs`), `routes/reports.py` (`/audit_log` admin-only + filtres), `templates/audit_log.html` (réécrit : 2 tableaux + pagination + filtres) | Seul `audit_log` existait (create/update/delete), sans enregistrement des connexions | Nouvelle table `login_logs` (user_id, username, action, ip_address, created_at) + `log_audit()` déjà utilisée pour les modifications | ✅ Ajouté 06-08-2026 |
| 11 | **`database is locked`** : archivage de produit + `log_audit` échouent | `db.py` (`get_db`, `_get_raw_connection`), `utils.py` (`log_audit`), `routes/products.py` (`delete_product`) | `log_audit()` ouvrait une **2e connexion** SQLite dans la transaction `with get_db()` encore ouverte → verrouillage mutuel (surtout quand la tâche APScheduler tournait toutes les 6h) → ni l'audit ni l'archivage ne s'écrivaient | (1) `log_audit()` réutilise la **connexion active** (`threading.local` + `SAVEPOINT` de protection) ; (2) `PRAGMA journal_mode=WAL` + `busy_timeout=30000` ; (3) dans `delete_product`, `log_audit` appelé **après** le commit | ✅ Corrigé 06-08-2026 (`4b12b10`) |
| 12 | **Nouvelle fonctionnalité** : colonne + filtre « Catégorie » sur les mouvements | `routes/movements.py`, `routes/reports.py`, `notifications.py` (rapport quotidien), templates + exports | Les mouvements n'affichaient pas la catégorie du produit | Colonne Catégorie ajoutée partout (liste, rapports, PDF, Excel) + filtre dans la page mouvements | ✅ Ajouté 07-08-2026 (`5ca1555`, `fe3f2fe`, `89381fd`) |
| 13 | **Nouvelle fonctionnalité** : audit avant/après sur les modifications | `utils.py` (`build_change_details`, `parse_change_details`), `routes/products.py`, `routes/movements.py` | L'audit ne montrait que la liste des champs modifiés sans les valeurs | Détails « champ → ancienne → nouvelle » affichés dans `/audit_log` | ✅ Ajouté 07-08-2026 (`d7ec99c`) |
| 14 | **Changement** : application **uniquement en français** | `routes/auth.py` (`change_language` force `fr`), `routes/main_routes.py` (`/change_language/ar` retiré), templates | Interface était bilingue ar/fr | Interface et notifications en français uniquement ; le lien de langue est supprimé | ✅ Fait 07-08-2026 (`a415c50`) |
| 15 | **Changement** : **archivage automatique désactivé** | `scheduler.py`, `db.py` | L'archivage automatique des produits inactifs (toutes les 6h) modifiait les données sans action utilisateur | Désactivé entièrement — aucune modification automatique des données ; seules les vérifications (expiration, stock bas) et le rapport quotidien restent actifs | ✅ Désactivé 07-08-2026 (`4ff165c`) |
| 16 | **Nouvelle fonctionnalité** : tableaux de bord par atelier + comparaison | `routes/workshops.py` (`/workshop_dashboard/<id>`, `/workshop_comparison`), templates dédiés | Pas de vue globale par atelier pour l'admin | Pages admin-only avec stats, graphiques et tableaux comparatifs | ✅ Ajouté 07-08-2026 (`6802428`) |
| 17 | **Nouvelle fonctionnalité** : **quantités décimales** | `db.py` (`_make_quantity_decimal`), `utils.py` (`parse_quantity`), `routes/products.py`, `routes/movements.py`, templates + exports | Quantités entières uniquement | Colonnes `quantity`/`min_quantity`/`theoretical_qty`/`actual_qty`/`difference` passées en `REAL` (SQLite accepte déjà les réels ; ALTER type requis pour PostgreSQL) + parsing/exports décimaux (2 décimales) | ✅ Ajouté 09-08-2026 (`76789a4`) |
| 18 | Rapport quotidien non reçu (23-08) ; erreurs SMTP `535 BadCredentials` récurrentes (07, 09, 12 et 23-08 10:48) | `notifications.py:474` (ancien), `scheduler.py:44` (ancien) | (a) L'anti-doublon comptait **toutes** les entrées `daily_report` du jour, y compris les échecs → un seul échec SMTP bloquait toute relance jusqu'au lendemain ; (b) job APScheduler en intervalle 24 h calé sur l'heure de démarrage uWSGI → heure d'envoie imprévisible | (a) Anti-doublon **par destinataire** comptant uniquement `status='sent'` → un échec ne bloque plus les relances ; (b) déclencheur cron fixe **19:00** tz `Africa/Casablanca` + relance automatique 20:30 ; garder l'envoi de rattrapage au démarrage. ⚠️ Cause racine des 535 : mot de passe d'application Gmail à régénérer + mettre à jour `EMAIL_PASSWORD` dans `.env` puis re-chiffrer | ✅ Corrigé 23-08-2026 |

---

## 6. Déploiement / synchronisation

### Local → GitHub (recommandé)
```bash
cd D:\Users\DT01\Desktop\stock2\projet_stock
git add <fichiers>
git commit -m "message descriptif"
git push
```

### Serveur → prendre les changements
```bash
cd ~/Engor/mysite && git pull
```
Puis **Reload** (Web tab).

### ⚠️ Points de vigilance
- Si on modifie des fichiers **directement sur le serveur** (console), les répliquer ensuite en local + `git push`, sinon un futur `git pull` risque un conflit.
- Si `git pull` refuse (« local changes would be overwritten ») et que les modifs locales sont identiques à GitHub :
  ```bash
  git checkout -- <fichiers> && git pull
  ```
- PythonAnywhere **gratuit** : pas de Scheduled Tasks ni Always-on → seul cron-job.org déclenche le rapport quotidien.

---

## 7. État actuel (09-08-2026)

- ✅ Rapport quotidien : envoyé aux **6** destinataires, statut `sent` (vérifié).
- ✅ Envoi automatique quotidien à **19:00** (cron-job.org, tz Casablanca) — seul déclencheur.
- ✅ Anti-doublon actif : réponse `{"message":"Already sent today","status":"skipped"}`.
- ✅ Correctifs #1, #2, #3 poussés sur GitHub (`33fb540`) et appliqués sur le serveur.
- ✅ Règle admin-only pour l'édition produit (`e21ec64`) et pour l'édition/suppression des mouvements (`7a354e3`) — appliquées sur le serveur.
- ✅ Journal de suivi : enregistrement des connexions/déconnexions (table `login_logs`) + `/audit_log` admin-only avec filtres + pagination (`01914a3`) — appliqué sur le serveur.
- ✅ Correctif `database is locked` (`4b12b10` + `02035d2`) : `log_audit` réutilise la connexion active + WAL + `log_audit` appelé après le commit dans `delete_product`. **Vérifié sur le serveur le 06-08-2026** : archivage + email de notification OK, entrée `delete product` présente dans `audit_log` (`FR00001 - FER TOR DIM 6`, par `admin`, 15:36:31), plus aucun `Failed to log audit` après le Reload.
- ✅ Test réel effectué : suppression du produit **FER TOR DIM 6** (FR00001) → archivé + journalisé + notification email reçue.
- ✅ (09-08-2026) **Langue française uniquement** (`a415c50`) : plus de lien de changement de langue ; interface/emails/rapports en français. Les libellés arabes de `translations.py` sont inactifs.
- ✅ (09-08-2026) **Quantités décimales** (`76789a4`) : migration `_make_quantity_decimal` + `parse_quantity` + exports 2 décimales. À tester sur le serveur après le prochain `git pull` + Reload (la migration tourne au démarrage).
- ✅ (09-08-2026) **Archivage automatique désactivé** (`4ff165c`) : plus aucune modification automatique de données (produits inactifs non archivés).
- ✅ (09-08-2026) **Tableaux de bord par atelier + comparaison** (`6802428`) : `/workshop_dashboard/<id>` et `/workshop_comparison`, réservés à l'admin.
- ⏳ À vérifier périodiquement : boîtes mail des destinataires (y compris Spam) après l'envoi quotidien.
- ⏳ **À faire** : déployer les nouveautés récentes (décimales, français uniquement, tableaux par atelier) sur le serveur PythonAnywhere (`git pull origin main` + Reload) et vérifier la migration des quantités.
