from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from werkzeug.utils import secure_filename
import uuid
import json # <-- Ajout du module json

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
DB_FILE = 'database.db'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
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
    ''') # Remplacement de image_url par images (pour stocker du JSON)
    
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

# --- ROUTES D'AUTHENTIFICATION ---
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if data.get('username') == 'admin' and data.get('password') == 'admin':
        return jsonify({"success": True, "message": "Connecté"})
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
        # Convertir la chaîne JSON en liste Python
        plan_dict['images'] = json.loads(plan_dict['images']) if plan_dict['images'] else []
        plans_list.append(plan_dict)
        
    return jsonify(plans_list)

@app.route('/api/plans', methods=['POST'])
def add_plan():
    title = request.form.get('title')
    description = request.form.get('description')
    
    # Récupérer plusieurs fichiers
    uploaded_files = request.files.getlist('images')
    image_urls = []
    
    for image_file in uploaded_files:
        if image_file and image_file.filename != '':
            ext = image_file.filename.rsplit('.', 1)[1].lower() if '.' in image_file.filename else 'png'
            filename = f"{uuid.uuid4().hex}.{ext}"
            image_file.save(os.path.join(UPLOAD_FOLDER, filename))
            image_urls.append(f"/uploads/{filename}")

    plan_id = uuid.uuid4().hex
    images_json = json.dumps(image_urls) # Convertir la liste en chaîne JSON
    
    conn = get_db_connection()
    conn.execute('INSERT INTO plans (id, title, description, images) VALUES (?, ?, ?, ?)',
                 (plan_id, title, description, images_json))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "id": plan_id})

@app.route('/api/plans/<plan_id>', methods=['DELETE'])
def delete_plan(plan_id):
    conn = get_db_connection()
    plan = conn.execute('SELECT images FROM plans WHERE id = ?', (plan_id,)).fetchone()
    
    # Supprimer toutes les images du serveur
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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True, port=5000)