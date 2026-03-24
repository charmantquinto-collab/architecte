from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename
import uuid
import json
from dotenv import load_dotenv # <-- 1. Ajout de l'import

# <-- 2. Charger les variables du fichier .env
load_dotenv() 

app = Flask(__name__)
# Limite les uploads à 16 Mégaoctets par requête
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": "*"}}) 

# <-- 3. Configuration via les variables d'environnement
app.secret_key = os.getenv('SECRET_KEY', 'cle_par_defaut_si_non_trouvee')
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', 'uploads')
DB_FILE = os.getenv('DATABASE_URL', 'database.db')

# <-- 4. Récupération des identifiants admin sécurisés
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'token_par_defaut_securise')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# NOUVEAU : Créer le dossier parent de la base de données s'il n'existe pas
db_dir = os.path.dirname(DB_FILE)
if db_dir:  # Vérifie si un chemin de dossier est spécifié (ex: 'instance')
    os.makedirs(db_dir, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    # Activer le mode WAL
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            images TEXT 
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            fb TEXT, ig TEXT, email TEXT, phone TEXT
        )
    ''')
    conn.execute('INSERT OR IGNORE INTO contacts (id, fb, ig, email, phone) VALUES (1, "", "", "", "")')
    conn.commit()
    conn.close()

init_db()

# 1. Création du protecteur de route
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # On s'attend à recevoir le token dans l'en-tête "Authorization"
        token = request.headers.get('Authorization')
        if not token or token != f"Bearer {ADMIN_TOKEN}":
            return jsonify({"success": False, "message": "Accès non autorisé"}), 403
        return f(*args, **kwargs)
    return decorated

# --- ROUTES D'AUTHENTIFICATION --- Mise à jour de la route de connexion
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == ADMIN_USERNAME and data.get('password') == ADMIN_PASSWORD:
        # On envoie le token au frontend en cas de succès
        return jsonify({"success": True, "message": "Connecté", "token": ADMIN_TOKEN})
    return jsonify({"success": False, "message": "Identifiants incorrects"}), 401

# --- ROUTES DES PLANS ---
@app.route('/api/plans', methods=['GET'])
def get_plans():
    conn = get_db_connection()
    plans = conn.execute('SELECT * FROM plans').fetchall()
    conn.close()
    
    plans_list = []
    for p in plans:
        plan_dict = dict(p)
        plan_dict['images'] = json.loads(plan_dict['images']) if plan_dict['images'] else []
        plans_list.append(plan_dict)
        
    return jsonify(plans_list)

@app.route('/api/plans', methods=['POST'])
@require_auth  # <-- Ajout de la protection ici
def add_plan():
    title = request.form.get('title')
    description = request.form.get('description')
    
    uploaded_files = request.files.getlist('images')
    image_urls = []
    
    for image_file in uploaded_files:
        if image_file and image_file.filename != '':
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'png'
            filename = f"{uuid.uuid4().hex}.{ext}"
            image_file.save(os.path.join(UPLOAD_FOLDER, filename))
            image_urls.append(f"/{UPLOAD_FOLDER}/{filename}") # Assure que le chemin correspond à la variable

    plan_id = uuid.uuid4().hex
    images_json = json.dumps(image_urls)
    
    conn = get_db_connection()
    conn.execute('INSERT INTO plans (id, title, description, images) VALUES (?, ?, ?, ?)',
                 (plan_id, title, description, images_json))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "id": plan_id})

@app.route('/api/plans/<plan_id>', methods=['DELETE'])
@require_auth  # <-- Ajout de la protection ici
def delete_plan(plan_id):
    conn = get_db_connection()
    plan = conn.execute('SELECT images FROM plans WHERE id = ?', (plan_id,)).fetchone()
    
    if plan and plan['images']:
        images_list = json.loads(plan['images'])
        for img_url in images_list:
            filename = img_url.split('/')[-1]
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            
    conn.execute('DELETE FROM plans WHERE id = ?', (plan_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# --- ROUTES DES CONTACTS ---
@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    conn = get_db_connection()
    contacts = conn.execute('SELECT * FROM contacts WHERE id = 1').fetchone()
    conn.close()
    return jsonify(dict(contacts))

@app.route('/api/contacts', methods=['POST'])
@require_auth  # <-- Ajout de la protection ici
def update_contacts():
    data = request.json
    conn = get_db_connection()
    conn.execute('''
        UPDATE contacts 
        SET fb = ?, ig = ?, email = ?, phone = ? 
        WHERE id = 1
    ''', (data.get('fb', ''), data.get('ig', ''), data.get('email', ''), data.get('phone', '')))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# <-- 6. Mise à jour de la route d'accès aux fichiers pour utiliser la variable UPLOAD_FOLDER
@app.route(f'/{UPLOAD_FOLDER}/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    # Flask_DEBUG peut aussi être récupéré du .env si souhaité : os.getenv('FLASK_DEBUG') == 'True'
    app.run(debug=True, port=5000)