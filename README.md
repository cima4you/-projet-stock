# 📦 Système de Gestion de Stock / نظام إدارة المخزون

Application Web de gestion d'inventaire en **français** (interface et notifications) développée avec **Flask**.

## ✨ Fonctionnalités / الميزات

| Français | العربية |
|----------|---------|
| ✅ Gestion des produits (CRUD, import/export Excel) | إدارة المنتجات (إضافة، تعديل، حذف، استيراد/تصدير إكسيل) |
| ✅ Mouvements de stock (Entrée/Sortie/Transfert) | حركات المخزون (دخول، خروج، تحويل) |
| ✅ Tableau de bord avec statistiques et graphiques | لوحة تحكم بإحصائيات ورسوم بيانية |
| ✅ Notifications email automatiques | إشعارات بريد إلكتروني تلقائية |
| ✅ Notifications WhatsApp (UltraMsg / CallMeBot) | إشعارات واتساب |
| ✅ Rapports PDF et Excel | تقارير PDF وإكسيل |
| ✅ Gestion des utilisateurs et rôles | إدارة المستخدمين والصلاحيات |
| ✅ Inventaire physique (comptage) | جرد فعلي للمخزون |
| ✅ Alertes stock bas et expiration | تنبيهات المخزون المنخفض وانتهاء الصلاحية |
| ✅ Quantités décimales | كميات عشرية (REAL, تنسيق بعلامتين عشريتين) |
| ✅ Journal de suivi (audit) avant/après + historique des connexions | سجل المتابعة (قبل/بعد) وسجل تسجيل الدخول |
| ✅ Multi-ateliers : tableaux de bord par atelier + comparaison | تعدد الورشات: لوحات تحكم لكل ورشة + مقارنة |
| ✅ Logo personnalisé | شعار مخصص |

## 🛠 Technologies / التقنيات

- **Backend**: Python 3.11+, Flask 3.1
- **Base de données**: SQLite (PostgreSQL sur Render via `DATABASE_URL`)
- **Frontend**: Bootstrap 5, Font Awesome 6
- **Email**: SMTP (Gmail)
- **WhatsApp**: UltraMsg API / CallMeBot
- **Rapports**: FPDF2, XlsxWriter, Pandas
- **Tâches planifiées**: APScheduler

## 🚀 Installation / التثبيت

```bash
# Cloner le projet
git clone https://github.com/cima4you/-projet-stock.git
cd projet_stock

# Installer les dépendances
pip install -r requirements.txt

# OU avec uv
uv sync
```

## ⚙ Configuration / الإعدادات

1. Copier `.env.example` vers `.env`
2. Remplir les informations :

```env
# Email
EMAIL_ADDRESS=votre@gmail.com
EMAIL_PASSWORD=votre_mot_de_passe_app

# WhatsApp (optionnel)
WHATSAPP_API_URL=https://api.ultramsg.com/instanceXXX/messages/chat
WHATSAPP_API_KEY=votre_token

# Sécurité
SESSION_SECRET=une_cle_secrete_unique
```

## ▶ Lancement / التشغيل

```bash
python main.py
```

Ouvrir [http://127.0.0.1:8050](http://127.0.0.1:8050)

**Identifiants par défaut :**
- Utilisateur : `admin`
- Mot de passe : `******`

## 📂 Structure du projet / هيكل المشروع

```
projet_stock/
├── main.py              # Point d'entrée
├── config.py            # Configuration (.env)
├── db.py                # Base de données (SQLite)
├── utils.py             # Fonctions utilitaires
├── csrf.py              # Protection CSRF
├── notifications.py     # Notifications email + WhatsApp
├── scheduler.py         # Tâches planifiées
├── protect_env.py       # Chiffrement .env
├── translations.py      # Libellés français (traductions ar/fr héritées, interface fr uniquement)
├── routes/
│   ├── auth.py          # Authentification
│   ├── dashboard.py     # Tableau de bord
│   ├── products.py      # Gestion des produits
│   ├── movements.py     # Mouvements de stock
│   ├── users.py         # Gestion des utilisateurs
│   ├── reports.py       # Rapports PDF/Excel
│   ├── categories.py    # Catégories
│   ├── suppliers.py     # Fournisseurs
│   ├── inventory.py     # Inventaire
│   ├── email_mgmt.py    # Gestion email
│   ├── whatsapp_mgmt.py # Gestion WhatsApp
│   └── ...
├── templates/           # Templates HTML
├── email_templates/     # Templates email
├── static/              # Fichiers statiques
└── uploads/             # Fichiers importés
```

## 🔒 Sécurité / الأمان

- Mots de passe hachés (Werkzeug)
- Protection CSRF
- Limitation de tentatives de connexion
- Rôles (user, admin, principal_admin)
- Chiffrement optionnel du fichier `.env`

## 📧 WhatsApp

Deux méthodes supportées :
1. **UltraMsg** ($39/mois après 3 jours d'essai)
2. **CallMeBot** (gratuit, nécessite activation)

## 🚀 Déploiement

- **Render** : le fichier `render.yaml` crée un Web Service + une base PostgreSQL automatiquement (gunicorn sur le port `$PORT`).
- **PythonAnywhere** : `git pull origin main` dans le dossier du site puis **Reload** de l'application web.

## 👤 Auteur

- **rachidbazighe** - bazigherachid@gmail.com
