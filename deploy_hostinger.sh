#!/bin/bash
# ============================================================
#  Script de déploiement sur VPS Hostinger (KVM) - projet_stock
#  À exécuter en ROOT via SSH après la livraison du VPS
#  Usage: bash deploy_hostinger.sh
# ============================================================
set -e

echo "============================================"
echo "  Déploiement projet_stock sur Hostinger VPS"
echo "============================================"

# ---------- Config ----------
APP_DIR="/var/www/projet_stock"
GIT_URL="https://github.com/cima4you/-projet-stock.git"
DOMAIN="${DOMAIN:-engor.stock.fr}"        # CHANGEZ si différent
SERVER_IP="$(hostname -I | awk '{print $1}')"

echo ""
echo "  ➜ Domaine : $DOMAIN"
echo "  ➜ IP serveur : $SERVER_IP"
echo ""
sleep 2

echo ""
echo "[1/7] Mise à jour du système..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

echo ""
echo "[2/7] Installation des dépendances système..."
apt-get install -y software-properties-common curl git nginx build-essential \
    python3 python3-pip python3-venv python3-dev

# Python 3.11+ (Ubuntu 22.04 a 3.10 par défaut → PPA deadsnakes)
CURPY=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "    Python système détecté : $CURPY"
if [ "$CURPY" = "3.10" ]; then
    echo "    Installation de Python 3.11 via deadsnakes..."
    add-apt-repository ppa:deadsnakes/ppa -y
    apt-get update -y
    apt-get install -y python3.11 python3.11-venv python3.11-dev
    PYBIN=$(command -v python3.11)
else
    PYBIN=$(command -v python3)
fi

echo ""
echo "[3/7] Récupération du code..."
mkdir -p /var/www
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull origin main
else
    git clone "$GIT_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo ""
echo "[4/7] Environnement virtuel + dépendances..."
"$PYBIN" -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

echo ""
echo "[5/7] Création du .env de production..."
cat > .env << EOF
SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
CRON_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=ChangezMoi-2026!
DEFAULT_ADMIN_EMAIL=bazigherachid@gmail.com
NOTIFICATION_EMAIL=bazigherachid@gmail.com
DAILY_REPORT_RECIPIENTS=bazigherachid@gmail.com
SECURE_COOKIE=1
EOF
chmod 600 .env

echo ""
echo "[6/7] Service systemd..."
cat > /etc/systemd/system/stock-app.service << 'EOF'
[Unit]
Description=projet_stock Flask (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/projet_stock
EnvironmentFile=/var/www/projet_stock/.env
ExecStart=/var/www/projet_stock/venv/bin/gunicorn main:app --bind 127.0.0.1:8050 --workers 1 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Autorisations
mkdir -p /var/www/projet_stock/uploads /var/www/projet_stock/static/logos
chown -R www-data:www-data /var/www/projet_stock
chmod -R 755 /var/www/projet_stock
chmod 600 /var/www/projet_stock/.env

systemctl daemon-reload
systemctl enable stock-app
systemctl start stock-app
echo "    Service démarré sur 127.0.0.1:8050"

echo ""
echo "[7/7] Configuration Nginx..."
cat > /etc/nginx/sites-available/stock-app << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 16M;

    location / {
        proxy_pass http://127.0.0.1:8050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/projet_stock/static/;
        expires 30d;
    }

    location /uploads/ {
        alias /var/www/projet_stock/uploads/;
    }
}
EOF
ln -sf /etc/nginx/sites-available/stock-app /etc/nginx/sites-enabled/stock-app
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo ""
echo "============================================"
echo "  Déploiement terminé avec succès ! 🎉"
echo "============================================"
echo ""
echo "  ➜ Site :    http://$SERVER_IP"
echo "  ➜ Utilisateur : admin"
echo "  ➜ Mot de passe : ChangezMoi-2026!  (À CHANGER après 1ère connexion)"
echo ""
echo "  PROCHAINES ÉTAPES DANS hPanel Hostinger :"
echo "   1. Pointez $DOMAIN vers $SERVER_IP (enregistrement A)"
echo "   2. Activez le HTTPS :"
echo "      sudo apt install -y certbot python3-certbot-nginx"
echo "      sudo certbot --nginx -d $DOMAIN"
echo "   3. Changez DEFAULT_ADMIN_PASSWORD dans /var/www/projet_stock/.env"
echo ""
echo "=========== FIN ============"