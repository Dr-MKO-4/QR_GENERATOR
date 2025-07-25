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
        img = Image.open(image_file)
        
        # Convertir en RGB si nécessaire
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Calculer la taille optimale
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        current_size = len(output.getvalue()) / 1024  # KB
        
        if current_size <= max_size_kb:
            output.seek(0)
            return output
        
        # Redimensionner si trop grande
        ratio = (max_size_kb / current_size) ** 0.5
        new_width = int(img.width * ratio)
        new_height = int(img.height * ratio)
        
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Essayer différentes qualités
        for quality in [75, 65, 55, 45]:
            output = io.BytesIO()
            img_resized.save(output, format='JPEG', quality=quality, optimize=True)
            if len(output.getvalue()) / 1024 <= max_size_kb:
                output.seek(0)
                return output
        
        # Dernière tentative avec qualité minimale
        output = io.BytesIO()
        img_resized.save(output, format='JPEG', quality=30, optimize=True)
        output.seek(0)
        return output
        
    except Exception as e:
        print(f"Erreur optimisation: {e}")
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

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_image():
    """Traite l'upload d'image et génère le QR code"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Format de fichier non supporté'}), 400
        
        # Nettoyer les anciennes images
        clean_old_images()
        
        # Générer un ID unique
        image_id = str(uuid.uuid4())
        
        # Optimiser l'image
        optimized_image = optimize_image(file, max_size_kb=500)
        
        # Sauvegarder l'image optimisée
        image_filename = f"{image_id}.jpg"
        image_path = os.path.join(IMAGES_DIR, image_filename)
        
        with open(image_path, 'wb') as f:
            f.write(optimized_image.read())
        
        # Créer l'URL de visualisation
        view_url = url_for('view_image', image_id=image_id, _external=True)
        
        # Générer le QR code
        qr_image = create_qr_code(view_url)
        if qr_image:
            qr_filename = f"qr_{image_id}.png"
            qr_path = os.path.join(QR_DIR, qr_filename)
            qr_image.save(qr_path)
        else:
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
        
        return jsonify({
            'success': True,
            'image_id': image_id,
            'view_url': view_url,
            'qr_url': url_for('serve_qr', image_id=image_id, _external=True),
            'download_qr_url': url_for('download_qr', image_id=image_id, _external=True)
        })
        
    except Exception as e:
        print(f"Erreur upload: {e}")
        return jsonify({'error': 'Erreur lors du traitement de l\'image'}), 500

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

@app.route('/stats')
def stats():
    """Page de statistiques"""
    data = load_image_data()
    total_images = len(data)
    total_size = sum(info.get('file_size', 0) for info in data.values())
    
    return jsonify({
        'total_images': total_images,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'platform_status': 'active'
    })

# Templates HTML intégrés
@app.before_first_request
def create_templates():
    """Crée les templates HTML"""
    os.makedirs('templates', exist_ok=True)
    
    # Template principal
    index_html = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QR Image Platform - Convertisseur d'Images en QR Code</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        .content {
            padding: 40px 30px;
        }
        .upload-zone {
            border: 3px dashed #667eea;
            border-radius: 15px;
            padding: 60px 20px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            margin-bottom: 30px;
        }
        .upload-zone:hover {
            border-color: #764ba2;
            background: #f8f9ff;
        }
        .upload-zone.dragover {
            border-color: #764ba2;
            background: #f0f4ff;
            transform: scale(1.02);
        }
        .upload-icon {
            font-size: 4rem;
            color: #667eea;
            margin-bottom: 20px;
        }
        .upload-text {
            font-size: 1.2rem;
            color: #555;
            margin-bottom: 20px;
        }
        .file-input {
            display: none;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 50px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-block;
            text-decoration: none;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .progress {
            display: none;
            margin: 20px 0;
        }
        .progress-bar {
            width: 100%;
            height: 10px;
            background: #f0f0f0;
            border-radius: 5px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s ease;
            animation: loading 2s infinite;
        }
        @keyframes loading {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        .result {
            display: none;
            text-align: center;
            padding: 30px;
            background: #f8f9ff;
            border-radius: 15px;
            margin-top: 30px;
        }
        .qr-preview {
            max-width: 300px;
            margin: 0 auto 20px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .result-links {
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 20px;
        }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 40px;
        }
        .feature {
            text-align: center;
            padding: 20px;
        }
        .feature-icon {
            font-size: 2.5rem;
            color: #667eea;
            margin-bottom: 15px;
        }
        .error {
            color: #e74c3c;
            background: #ffeaea;
            padding: 15px;
            border-radius: 10px;
            margin: 20px 0;
            display: none;
        }
        @media (max-width: 768px) {
            .header h1 { font-size: 2rem; }
            .content { padding: 20px; }
            .result-links { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔗 QR Image Platform</h1>
            <p>Convertissez vos images en codes QR accessibles partout dans le monde</p>
        </div>
        
        <div class="content">
            <div class="upload-zone" onclick="document.getElementById('imageFile').click()">
                <div class="upload-icon">📷</div>
                <div class="upload-text">
                    Cliquez ici ou glissez votre image<br>
                    <small>Formats supportés: JPG, PNG, GIF, BMP, WebP (Max 10MB)</small>
                </div>
                <button class="btn">Choisir une image</button>
            </div>
            
            <input type="file" id="imageFile" class="file-input" accept="image/*">
            
            <div class="error" id="errorMsg"></div>
            
            <div class="progress" id="progress">
                <div class="progress-bar">
                    <div class="progress-fill"></div>
                </div>
                <p>Traitement de votre image...</p>
            </div>
            
            <div class="result" id="result">
                <h3>✅ QR Code généré avec succès !</h3>
                <img id="qrPreview" class="qr-preview" alt="QR Code">
                <p>Scannez ce QR code avec n'importe quel smartphone pour voir votre image</p>
                <div class="result-links">
                    <a id="viewLink" class="btn" target="_blank">👀 Voir l'image</a>
                    <a id="downloadQrLink" class="btn" download>⬇️ Télécharger QR</a>
                </div>
            </div>
            
            <div class="features">
                <div class="feature">
                    <div class="feature-icon">🌍</div>
                    <h3>Accessible Partout</h3>
                    <p>Vos QR codes fonctionnent dans le monde entier, aucune limitation géographique</p>
                </div>
                <div class="feature">
                    <div class="feature-icon">📱</div>
                    <h3>Compatible Mobile</h3>
                    <p>Fonctionne avec tous les smartphones et applications de scan QR</p>
                </div>
                <div class="feature">
                    <div class="feature-icon">🔒</div>
                    <h3>Sécurisé</h3>
                    <p>Images automatiquement supprimées après 7 jours pour votre sécurité</p>
                </div>
                <div class="feature">
                    <div class="feature-icon">⚡</div>
                    <h3>Rapide</h3>
                    <p>Optimisation automatique pour des QR codes de qualité optimale</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        const uploadZone = document.querySelector('.upload-zone');
        const fileInput = document.getElementById('imageFile');
        const errorMsg = document.getElementById('errorMsg');
        const progress = document.getElementById('progress');
        const result = document.getElementById('result');

        // Drag & Drop
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });

        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });

        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFile(files[0]);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });

        function showError(message) {
            errorMsg.textContent = message;
            errorMsg.style.display = 'block';
            progress.style.display = 'none';
            result.style.display = 'none';
        }

        function hideError() {
            errorMsg.style.display = 'none';
        }

        function handleFile(file) {
            hideError();
            
            // Vérifications
            if (!file.type.startsWith('image/')) {
                showError('Veuillez sélectionner un fichier image valide.');
                return;
            }
            
            if (file.size > 10 * 1024 * 1024) {
                showError('Le fichier est trop volumineux (max 10MB).');
                return;
            }

            // Afficher le progrès
            progress.style.display = 'block';
            result.style.display = 'none';

            // Préparer les données
            const formData = new FormData();
            formData.append('image', file);

            // Envoyer la requête
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                progress.style.display = 'none';
                
                if (data.success) {
                    // Afficher le résultat
                    document.getElementById('qrPreview').src = data.qr_url;
                    document.getElementById('viewLink').href = data.view_url;
                    document.getElementById('downloadQrLink').href = data.download_qr_url;
                    result.style.display = 'block';
                } else {
                    showError(data.error || 'Erreur lors du traitement de l\'image.');
                }
            })
            .catch(error => {
                progress.style.display = 'none';
                showError('Erreur de connexion. Veuillez réessayer.');
                console.error('Error:', error);
            });
        }
    </script>
</body>
</html>'''

    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)

    # Template de visualisation
    view_html = '''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image partagée - QR Image Platform</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            max-width: 90%;
            max-height: 90vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .content {
            padding: 30px;
            text-align: center;
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .image-container {
            margin: 20px 0;
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        img {
            max-width: 100%;
            max-height: 70vh;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        .info {
            margin-top: 20px;
            color: #666;
        }
        .btn {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 25px;
            text-decoration: none;
            border-radius: 25px;
            margin: 10px;
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .footer {
            padding: 20px;
            text-align: center;
            background: #f8f9ff;
            border-top: 1px solid #eee;
        }
        .footer a {
            color: #667eea;
            text-decoration: none;
        }
        @media (max-width: 768px) {
            .container { max-width: 95%; }
            .content { padding: 20px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>📷 Image Partagée</h2>
            <p>Via QR Image Platform</p>
        </div>
        
        <div class="content">
            <div class="image-container">
                <img src="{{ url_for('serve_image', image_id=image_id) }}" 
                     alt="Image partagée via QR Code"
                     loading="lazy">
            </div>
            
            <div class="info">
                <p><strong>Image:</strong> {{ image_info.original_name }}</p>
                <p><strong>Partagée le:</strong> {{ image_info.upload_time[:10] }}</p>
            </div>
            
            <div>
                <a href="{{ url_for('serve_image', image_id=image_id) }}" 
                   class="btn" download>⬇️ Télécharger</a>
            </div>
        </div>
        
        <div class="footer">
            <p>Créé avec <a href="{{ url_for('index') }}">QR Image Platform</a> 🔗</p>
        </div>
    </div>
</body>
</html>'''

    with open('templates/view_image.html', 'w', encoding='utf-8') as f:
        f.write(view_html)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)