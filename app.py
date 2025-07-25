#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plateforme Web QR Image - Déployable sur Render
Convertit des images en codes QR accessibles partout dans le monde
"""

from flask import Flask, request, render_template, jsonify, send_file, url_for, redirect
import qrcode
import os
import uuid
import time
from PIL import Image
import io
import base64
from werkzeug.utils import secure_filename
import hashlib
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'qr-image-platform-secret-key-2024')

# Configuration pour le stockage (en production, utilisez une base de données)
IMAGES_DIR = 'static/images'
QR_DIR = 'static/qr_codes'
DATA_FILE = 'image_data.json'

# Créer les dossiers nécessaires
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)
os.makedirs('static', exist_ok=True)

# Extensions autorisées
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}

def allowed_file(filename):
    """Vérifie si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_image_data():
    """Charge les données des images depuis le fichier JSON"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        print(f"Erreur chargement des données: {DATA_FILE} non trouvé ou corrompu.")
        pass
    return {}

def save_image_data(data):
    """Sauvegarde les données des images dans le fichier JSON"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erreur sauvegarde: {e}")

def clean_old_images():
    """Nettoie les anciennes images (plus de 7 jours)"""
    try:
        data = load_image_data()
        current_time = datetime.now()
        to_remove = []
        
        for image_id, info in data.items():
            upload_time = datetime.fromisoformat(info.get('upload_time', '2024-01-01T00:00:00'))
            if current_time - upload_time > timedelta(days=7):
                to_remove.append(image_id)
                
                # Supprimer les fichiers
                try:
                    if os.path.exists(info.get('image_path', '')):
                        os.remove(info['image_path'])
                    if os.path.exists(info.get('qr_path', '')):
                        os.remove(info['qr_path'])
                except:
                    pass
        
        # Mettre à jour les données
        for image_id in to_remove:
            data.pop(image_id, None)
            
        if to_remove:
            save_image_data(data)
            print(f"Nettoyage: {len(to_remove)} images supprimées")
            
    except Exception as e:
        print(f"Erreur nettoyage: {e}")

def optimize_image(image_file, max_size_kb=500):
    """Optimise une image pour réduire sa taille"""
    try:
        print(f"Début optimisation, taille max: {max_size_kb}KB")
        
        # Reset file pointer et lire l'image
        image_file.seek(0)
        img = Image.open(image_file)
        print(f"Image originale: {img.size}, mode: {img.mode}")
        
        # Convertir en RGB si nécessaire
        if img.mode in ('RGBA', 'LA', 'P'):
            print(f"Conversion du mode {img.mode} vers RGB")
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1] if len(img.split()) > 3 else None)
            img = background
        
        # Redimensionner si l'image est trop grande
        max_dimension = 1920
        if img.width > max_dimension or img.height > max_dimension:
            print(f"Redimensionnement de {img.size}")
            ratio = min(max_dimension / img.width, max_dimension / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            print(f"Nouvelle taille: {img.size}")
        
        # Essayer différentes qualités JPEG
        for quality in [85, 75, 65, 55, 45, 35]:
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            current_size_kb = len(output.getvalue()) / 1024
            print(f"Qualité {quality}: {current_size_kb:.1f}KB")
            
            if current_size_kb <= max_size_kb:
                output.seek(0)
                print(f"Optimisation réussie: {current_size_kb:.1f}KB")
                return output
        
        # Si toujours trop grande, réduire encore la taille
        for scale in [0.8, 0.6, 0.4]:
            new_size = (int(img.width * scale), int(img.height * scale))
            img_scaled = img.resize(new_size, Image.Resampling.LANCZOS)
            
            output = io.BytesIO()
            img_scaled.save(output, format='JPEG', quality=30, optimize=True)
            current_size_kb = len(output.getvalue()) / 1024
            print(f"Échelle {scale}: {current_size_kb:.1f}KB")
            
            if current_size_kb <= max_size_kb:
                output.seek(0)
                print(f"Optimisation réussie avec mise à l'échelle: {current_size_kb:.1f}KB")
                return output
        
        # Dernière tentative avec qualité minimale
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=20, optimize=True)
        output.seek(0)
        final_size_kb = len(output.getvalue()) / 1024
        print(f"Optimisation finale: {final_size_kb:.1f}KB")
        return output
        
    except Exception as e:
        print(f"Erreur optimisation: {e}")
        import traceback
        traceback.print_exc()
        # En cas d'erreur, retourner le fichier original
        image_file.seek(0)
        return image_file

def create_qr_code(url, size=10):
    """Crée un code QR pour l'URL donnée"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=size,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        qr_image = qr.make_image(fill_color="black", back_color="white")
        return qr_image
    except Exception as e:
        print(f"Erreur création QR: {e}")
        return None

def create_templates():
    """Crée les templates HTML"""
    os.makedirs('templates', exist_ok=True)
    
    # Template principal
    index_html = '''<!DOCTYPE html>
<!-- templates/index.html -->
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Image Platform - Convertisseur d'Images en QR Code</title>
  <style>
    :root {
      --primary: #5a67d8;
      --primary-dark: #4c51bf;
      --background: #f7fafc;
      --surface: #ffffff;
      --text: #2d3748;
      --accent: #ed64a6;
      --radius: 12px;
      --transition: 0.3s;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: var(--background);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .container {
      width: 100%; max-width: 720px;
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: 0 8px 24px rgba(0,0,0,0.1);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    header {
      background: var(--primary);
      color: #fff;
      padding: 32px;
      text-align: center;
    }
    header h1 { font-size: 2rem; }
    header p { margin-top: 8px; opacity: 0.8; }
    main {
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    .upload-zone {
      border: 2px dashed var(--primary-dark);
      border-radius: var(--radius);
      padding: 48px;
      text-align: center;
      cursor: pointer;
      transition: background var(--transition), border-color var(--transition);
    }
    .upload-zone:hover,
    .upload-zone.dragover {
      background: rgba(90, 103, 216, 0.1);
      border-color: var(--accent);
    }
    .upload-zone span { display: block; font-size: 1.25rem; margin-top: 12px; }
    .file-input { display: none; }
    .btn {
      display: inline-block;
      background: var(--primary);
      color: #fff;
      padding: 12px 28px;
      border: none;
      border-radius: var(--radius);
      font-size: 1rem;
      cursor: pointer;
      text-decoration: none;
      transition: transform var(--transition), box-shadow var(--transition);
    }
    .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(90,103,216,0.3); }
    .error {
      display: none;
      background: #ffe3e3;
      color: #c53030;
      padding: 16px;
      border-radius: var(--radius);
      text-align: center;
    }
    .progress {
      display: none;
      width: 100%;
      text-align: center;
    }
    .progress-bar {
      width: 100%; height: 8px;
      background: #e2e8f0;
      border-radius: 4px;
      overflow: hidden;
    }
    .progress-fill {
      width: 0%; height: 100%;
      background: var(--primary);
      transition: width var(--transition);
    }
    .result {
      display: none;
      background: #f0f9ff;
      border-radius: var(--radius);
      padding: 24px;
      text-align: center;
      box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }
    .qr-preview { width: 200px; height: 200px; margin: 0 auto 16px; }
    .result-links { display: flex; gap: 16px; flex-wrap: wrap; justify-content: center; }
    .features {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px,1fr));
      gap: 16px;
    }
    .feature { text-align: center; }
    .feature-icon { font-size: 2rem; color: var(--primary); margin-bottom: 8px; }
    @media (max-width: 600px) {
      header h1 { font-size: 1.75rem; }
      main { padding: 16px; gap: 16px; }
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🔗 QR Image Platform</h1>
      <p>Convertissez vos images en codes QR accessibles partout dans le monde</p>
    </header>
    <main>
      <div class="upload-zone" onclick="fileInput.click()">
        <div>📷</div>
        <span>Cliquez ou glissez-déposez votre image (Max 10MB)</span>
        <button class="btn">Choisir un fichier</button>
      </div>
      <input type="file" id="imageFile" class="file-input" accept="image/*">
      <div class="error" id="errorMsg"></div>
      <div class="progress" id="progress">
        <div class="progress-bar"><div class="progress-fill"></div></div>
        <p>Traitement en cours...</p>
      </div>
      <div class="result" id="result">
        <h3>✅ QR Code généré !</h3>
        <img id="qrPreview" class="qr-preview" alt="QR Code">
        <div class="result-links">
          <a id="viewLink" class="btn" target="_blank">Voir l'image</a>
          <a id="downloadQrLink" class="btn" download>Télécharger QR</a>
        </div>
      </div>
      <div class="features">
        <div class="feature"><div class="feature-icon">🌍</div><h4>Accessible Partout</h4></div>
        <div class="feature"><div class="feature-icon">📱</div><h4>Compatible Mobile</h4></div>
        <div class="feature"><div class="feature-icon">🔒</div><h4>Sécurisé</h4></div>
        <div class="feature"><div class="feature-icon">⚡</div><h4>Rapide</h4></div>
      </div>
    </main>
  </div>
  <script>
    const uploadZone = document.querySelector('.upload-zone');
    const fileInput = document.getElementById('imageFile');
    const errorMsg = document.getElementById('errorMsg');
    const progress = document.getElementById('progress');
    const result = document.getElementById('result');

    ['dragover','dragleave','drop'].forEach(evt => {
      uploadZone.addEventListener(evt, e => e.preventDefault());
    });
    uploadZone.addEventListener('dragover', () => uploadZone.classList.add('dragover'));
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', e => {
      uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', e => handleFile(e.target.files[0]));

    function showError(msg) {
      errorMsg.textContent = msg;
      errorMsg.style.display = 'block';
      progress.style.display = 'none';
      result.style.display = 'none';
    }
    function hideError() {
      errorMsg.style.display = 'none';
    }

    function handleFile(file) {
      hideError();
      if (!file.type.startsWith('image/')) return showError('Fichier non image');
      if (file.size > 10*1024*1024) return showError('Trop volumineux');
      progress.style.display = 'block'; result.style.display = 'none';
      const form = new FormData(); form.append('image', file);
      fetch('/upload', { method:'POST', body:form })
        .then(res => res.ok ? res.json() : Promise.reject(res.status))
        .then(data => {
          progress.style.display='none';
          if (data.success) {
            document.getElementById('qrPreview').src=data.qr_url;
            document.getElementById('viewLink').href=data.view_url;
            document.getElementById('downloadQrLink').href=data.download_qr_url;
            result.style.display='block';
          } else showError(data.error);
        })
        .catch(() => showError('Erreur réseau'));
    }
  </script>
</body>
</html>
'''

    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)

    # Template de visualisation
    view_html = '''<!DOCTYPE html>
<!-- templates/view.html -->
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Image partagée - QR Image Platform</title>
  <style>
    :root {
      --primary: #5a67d8;
      --background: #f7fafc;
      --surface: #ffffff;
      --text: #2d3748;
      --radius: 12px;
      --transition: 0.3s;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', sans-serif;
      background: var(--background);
      color: var(--text);
      display: flex; justify-content: center; align-items: center;
      height: 100vh; padding: 16px;
    }
    .card {
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: 0 8px 24px rgba(0,0,0,0.1);
      overflow: hidden;
      max-width: 600px;
      width: 100%;
      display: flex; flex-direction: column;
    }
    .card header {
      background: var(--primary);
      color: #fff;
      padding: 24px;
      text-align: center;
    }
    .card .content {
      padding: 24px;
      text-align: center;
      display: flex; flex-direction: column; gap: 16px;
    }
    .card img {
      max-width: 100%; border-radius: var(--radius);
      box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }
    .info { font-size: 0.9rem; color: #4a5568; }
    .btn {
      padding: 10px 24px;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: var(--radius);
      text-decoration: none;
      transition: transform var(--transition);
    }
    .btn:hover { transform: translateY(-2px); }
    .footer {
      background: #edf2f7;
      text-align: center;
      padding: 16px;
      font-size: 0.85rem;
    }
  </style>
</head>
<body>
  <div class="card">
    <header>
      <h2>📷 Image Partagée</h2>
      <p>QR Image Platform</p>
    </header>
    <div class="content">
      <img src="{{ url_for('serve_image', image_id=image_id) }}" alt="Image partagée">
      <div class="info">
        <p><strong>Nom:</strong> {{ image_info.original_name }}</p>
        <p><strong>Upload le:</strong> {{ image_info.upload_time[:10] }}</p>
      </div>
      <a href="{{ url_for('serve_image', image_id=image_id) }}" class="btn" download>⬇️ Télécharger</a>
    </div>
    <div class="footer">
      Créé avec <a href="{{ url_for('index') }}">QR Image Platform</a>
    </div>
  </div>
</body>
</html>
'''

    with open('templates/view_image.html', 'w', encoding='utf-8') as f:
        f.write(view_html)

# Créer les templates au démarrage de l'application
create_templates()

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    """Traite l'upload d'image et génère le QR code"""
    try:
        print("=== DEBUT UPLOAD ===")
        print(f"Files reçus: {list(request.files.keys())}")
        print(f"Form data: {list(request.form.keys())}")
        
        if 'image' not in request.files:
            print("ERREUR: Aucun fichier 'image' dans la requête")
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        file = request.files['image']
        print(f"Fichier reçu: {file.filename}, taille: {file.content_length}")
        
        if file.filename == '':
            print("ERREUR: Nom de fichier vide")
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        if not allowed_file(file.filename):
            print(f"ERREUR: Extension non autorisée pour {file.filename}")
            return jsonify({'error': 'Format de fichier non supporté. Utilisez: PNG, JPG, JPEG, GIF, BMP, WebP'}), 400
        
        # Nettoyer les anciennes images
        clean_old_images()
        
        # Générer un ID unique
        image_id = str(uuid.uuid4())
        print(f"ID généré: {image_id}")
        
        # Optimiser l'image
        print("Optimisation de l'image...")
        file.seek(0)  # Reset file pointer
        optimized_image = optimize_image(file, max_size_kb=500)
        
        # Sauvegarder l'image optimisée
        image_filename = f"{image_id}.jpg"
        image_path = os.path.join(IMAGES_DIR, image_filename)
        print(f"Sauvegarde vers: {image_path}")
        
        with open(image_path, 'wb') as f:
            optimized_image.seek(0)
            f.write(optimized_image.read())
        
        print(f"Image sauvegardée, taille: {os.path.getsize(image_path)} bytes")
        
        # Créer l'URL de visualisation
        view_url = url_for('view_image', image_id=image_id, _external=True)
        print(f"URL de visualisation: {view_url}")
        
        # Générer le QR code
        print("Génération du QR code...")
        qr_image = create_qr_code(view_url)
        if qr_image:
            qr_filename = f"qr_{image_id}.png"
            qr_path = os.path.join(QR_DIR, qr_filename)
            qr_image.save(qr_path)
            print(f"QR code sauvegardé: {qr_path}")
        else:
            print("ERREUR: Impossible de générer le QR code")
            return jsonify({'error': 'Erreur lors de la génération du QR code'}), 500
        
        # Sauvegarder les métadonnées
        data = load_image_data()
        data[image_id] = {
            'original_name': secure_filename(file.filename),
            'image_path': image_path,
            'qr_path': qr_path,
            'upload_time': datetime.now().isoformat(),
            'view_url': view_url,
            'file_size': os.path.getsize(image_path)
        }
        save_image_data(data)
        print("Métadonnées sauvegardées")
        
        response_data = {
            'success': True,
            'image_id': image_id,
            'view_url': view_url,
            'qr_url': url_for('serve_qr', image_id=image_id, _external=True),
            'download_qr_url': url_for('download_qr', image_id=image_id, _external=True)
        }
        print(f"=== UPLOAD REUSSI === {response_data}")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"ERREUR UPLOAD: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Erreur lors du traitement: {str(e)}"}), 500

@app.route('/view/<image_id>')
def view_image(image_id):
    """Affiche l'image dans une page web"""
    data = load_image_data()
    if image_id not in data:
        return "Image non trouvée ou expirée", 404
    
    image_info = data[image_id]
    return render_template('view_image.html', 
                         image_id=image_id,
                         image_info=image_info)

@app.route('/image/<image_id>')
def serve_image(image_id):
    """Sert l'image directement"""
    data = load_image_data()
    if image_id not in data:
        return "Image non trouvée", 404
    
    image_path = data[image_id]['image_path']
    if not os.path.exists(image_path):
        return "Fichier non trouvé", 404
    
    return send_file(image_path)

@app.route('/qr/<image_id>')
def serve_qr(image_id):
    """Sert le QR code directement"""
    data = load_image_data()
    if image_id not in data:
        return "QR code non trouvé", 404
    
    qr_path = data[image_id]['qr_path']
    if not os.path.exists(qr_path):
        return "QR code non trouvé", 404
    
    return send_file(qr_path)

@app.route('/download-qr/<image_id>')
def download_qr(image_id):
    """Télécharge le QR code"""
    data = load_image_data()
    if image_id not in data:
        return "QR code non trouvé", 404
    
    qr_path = data[image_id]['qr_path']
    if not os.path.exists(qr_path):
        return "QR code non trouvé", 404
    
    return send_file(qr_path, as_attachment=True, 
                    download_name=f"qr_code_{image_id}.png")

@app.route('/favicon.ico')
def favicon():
    """Serve a simple favicon to avoid 404 errors"""
    return '', 204
    """Page de statistiques"""
    data = load_image_data()
    total_images = len(data)
    total_size = sum(info.get('file_size', 0) for info in data.values())
    
    return jsonify({
        'total_images': total_images,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'platform_status': 'active'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
