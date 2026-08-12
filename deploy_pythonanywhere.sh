#!/bin/bash
# Deployment script for PythonAnywhere
# Run this from the PythonAnywhere Bash console

set -e

PROJECT_DIR=~/projet_stock
PROJECT_URL=https://github.com/cima4you/-projet-stock.git

echo "=== Cloning project ==="
cd ~
if [ -d "$PROJECT_DIR" ]; then
    echo "Project already exists, pulling latest..."
    cd "$PROJECT_DIR"
    git pull
else
    git clone "$PROJECT_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

echo "=== Creating virtual environment ==="
python3.11 -m venv venv
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Creating .env file ==="
if [ ! -f .env ]; then
    cat > .env << 'EOF'
SESSION_SECRET=pa_$(openssl rand -hex 32)
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_PASSWORD=$(openssl rand -base64 18)
DEFAULT_ADMIN_EMAIL=bazigherachid@gmail.com
EOF
    echo ".env file created"
else
    echo ".env already exists, skipping"
fi

echo "=== Creating static directories ==="
mkdir -p static/css static/js static/images static/logos uploads

echo ""
echo "=== Deployment ready! ==="
echo ""
echo "Now go to PythonAnywhere Dashboard > Web and:"
echo "1. Add a new web app (Manual config, Python 3.11)"
echo "2. Set source code: $PROJECT_DIR"
echo "3. Set working directory: $PROJECT_DIR"
echo "4. Set virtual env: $PROJECT_DIR/venv"
echo "5. Edit WSGI file with content from: $PROJECT_DIR/pythonanywhere_wsgi.py"
echo "6. Add static files mapping:"
echo "   URL: /static/   Directory: $PROJECT_DIR/static"
echo "7. Reload the web app"
echo ""
echo "Your app will be at: https://bazighe.pythonanywhere.com"