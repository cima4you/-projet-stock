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
| CRON_SECRET (serveur) | `RapportQuotidien2024` (différent du local `.env` : `123*5487/-`) |
| Déclencheur rapport quotidien | cron-job.org, job « Rapport quotidien stock », **19:00** tz `Africa/Casablanca`, URL `/cron/daily-report?token=RapportQuotidien2024` |

---

## 2. Flux principaux (عمل التطبيق)

### Authentification
1. `routes/auth.py` : login → stocke `workshop_id` + `workshop_name` dans la session.
2. Toutes les routes de données utilisent `workshop_filter()` de `utils.py` pour filtrer par atelier.
3. Rôles : `user`, `admin`, `principal_admin`. Admin par défaut : `admin` / `bj319260`.

### Produits & mouvements
- `routes/products.py` : ajout/modification produit → insère aussi un `stock_movements` (entry/exit).
- `routes/movements.py` : mouvements avec types `entry`, `exit`, `transfert`.
- Table : `stock_movements` (pas `movements` !).

### Notifications d'ajout produit
- `notifications.py` `send_product_addition_notification()` : envoie un email (FR/AR) aux destinataires de l'atelier.
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
- **Liste actuelle (5)** :
  1. bazigherachid@gmail.com
  2. rbazighe@gmail.com
  3. hmiddouchhamza@gmail.com
  4. younesghazzali1995@gmail.com
  5. mohammed.chabli@engor.net

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
curl -s "https://bazighe82.pythonanywhere.com/cron/daily-report?token=RapportQuotidien2024"
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

## 7. État actuel (04-08-2026)

- ✅ Rapport quotidien : envoyé aux **5** destinataires, statut `sent` (vérifié).
- ✅ Envoi automatique quotidien à **19:00** (cron-job.org, tz Casablanca) — seul déclencheur.
- ✅ Anti-doublon actif : réponse `{"message":"Already sent today","status":"skipped"}`.
- ✅ Données intactes : 20 produits, 57 mouvements.
- ✅ Correctifs #1, #2, #3 poussés sur GitHub (`33fb540`) et appliqués sur le serveur.
- ✅ Règle admin-only pour l'édition produit poussée sur GitHub (`e21ec64`) et appliquée sur le serveur (fast-forward → `git pull` OK 04-08-2026).
- ⏳ À vérifier périodiquement : boîtes mail des destinataires (y compris Spam) après l'envoi quotidien.
