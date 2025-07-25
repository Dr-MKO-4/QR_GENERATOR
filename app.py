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
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Image Platform</title>
  <style>
    :root {
      /* Light Colors */
      --bg: #f0f2f5;
      --surface: #fff;
      --text: #333;
      --primary: #5a67d8; /* Indigo 600 */
      --primary-dark: #4c52af; /* Slightly darker primary for hover/active */
      --accent: #ed64a6; /* Pink 400 */
      --radius: 12px;
      --transition: 0.3s ease;
      --shadow-light: 0 12px 40px rgba(0,0,0,0.08);
      --shadow-hover: 0 16px 48px rgba(0,0,0,0.12);
    }
    [data-theme="dark"] {
      /* Dark Colors */
      --bg: #1a202c; /* Gray 900 */
      --surface: #2d3748; /* Gray 800 */
      --text: #e2e8f0; /* Gray 200 */
      --primary: #667eea; /* Indigo 500 */
      --primary-dark: #556be7;
      --accent: #f687b3; /* Pink 300 */
      --shadow-light: 0 12px 40px rgba(0,0,0,0.2);
      --shadow-hover: 0 16px 48px rgba(0,0,0,0.3);
    }

    /* Base Reset & Typography */
    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    html {
      scroll-behavior: smooth;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      transition: background var(--transition), color var(--transition);
      -webkit-font-smoothing: antialiased; /* Smoother fonts on macOS/iOS */
      -moz-osx-font-smoothing: grayscale;
    }

    /* Container */
    .container {
      width: 100%;
      max-width: 800px;
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: var(--shadow-light);
      overflow: hidden;
      transition: background var(--transition), box-shadow var(--transition);
    }

    /* Header */
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--primary);
      padding: 24px;
      color: #fff;
      position: relative;
      z-index: 10;
    }
    header h1 {
      font-size: 1.75rem;
      font-weight: 700;
    }

    /* Theme Toggle */
    .theme-toggle {
      background: none;
      border: none;
      cursor: pointer;
      width: 32px;
      height: 32px;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%; /* Make it a circle */
      transition: transform var(--transition), background-color var(--transition);
    }
    .theme-toggle:focus-visible { /* Modern focus outline */
      outline: 2px solid #fff;
      outline-offset: 2px;
    }
    .theme-toggle:hover {
      transform: scale(1.1);
      background-color: rgba(255,255,255,0.1); /* Subtle hover background */
    }
    .theme-toggle svg {
      width: 100%;
      height: 100%;
      fill: currentColor; /* Use current text color for SVG */
      transition: fill var(--transition);
    }
    /* Specific styling for sun/moon parts */
    [data-theme="light"] .theme-toggle .moon { display: none; }
    [data-theme="dark"] .theme-toggle .sun { display: none; }


    /* Main Content */
    main {
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 32px;
    }

    /* Upload Zone */
    .upload-zone {
      position: relative;
      border: 2px dashed var(--primary);
      border-radius: var(--radius);
      padding: 40px; /* Reduced padding slightly */
      text-align: center;
      /* cursor: pointer; REMOVED: Only button is clickable now */
      overflow: hidden;
      transition: background var(--transition), border-color var(--transition);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 16px; /* Spacing between elements */
    }
    .upload-zone::after {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: radial-gradient(circle at center, rgba(90,103,216,0.1) 0%, transparent 70%); /* More subtle, primary-based radial */
      opacity: 0;
      transition: opacity 0.8s ease-in-out; /* Faster fade in */
      animation: pulse 2.5s infinite cubic-bezier(0.4, 0, 0.6, 1); /* Smoother pulse */
      z-index: 1; /* Ensure it's above background but below content */
      pointer-events: none; /* Allow clicks to pass through */
    }
    .upload-zone:hover {
      border-color: var(--accent);
      background: rgba(90,103,216,0.05); /* Lighter background on hover */
    }
    .upload-zone:hover::after {
      opacity: 1;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(0.98); opacity: 0.8; }
      50% { transform: scale(1.02); opacity: 1; }
    }
    .upload-zone svg {
      width: 52px; /* Slightly larger icon */
      height: 52px;
      fill: var(--primary);
      margin-bottom: 8px; /* Adjusted margin */
      position: relative;
      z-index: 2;
    }
    .upload-zone span {
      display: block;
      font-size: 1.15rem; /* Slightly smaller text */
      font-weight: 500;
      margin-bottom: 8px; /* Adjusted margin */
      position: relative;
      z-index: 2;
    }
    .file-input {
      display: none;
    }

    /* Buttons */
    .btn {
      display: inline-flex; /* Use flex for centering content */
      align-items: center;
      justify-content: center;
      background: var(--primary);
      color: #fff;
      padding: 12px 28px;
      border: none;
      border-radius: var(--radius);
      cursor: pointer;
      text-decoration: none;
      font-weight: 600;
      transition: transform var(--transition), box-shadow var(--transition), background-color var(--transition);
      position: relative;
      z-index: 2; /* Ensure button is above pulse effect */
    }
    .btn:hover {
      transform: translateY(-3px); /* More pronounced lift */
      background-color: var(--primary-dark);
      box-shadow: 0 8px 25px rgba(0,0,0,0.15); /* Stronger shadow */
    }
    .btn:active {
      transform: translateY(0);
      box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .btn:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 3px;
    }

    /* Error Message */
    .error {
      display: none;
      background: #fee2e2; /* Red 100 */
      color: #b91c1c; /* Red 700 */
      padding: 16px;
      border-radius: var(--radius);
      text-align: center;
      margin-top: -16px; /* Overlap with previous section slightly */
      position: relative;
      z-index: 1;
      font-weight: 500;
      border: 1px solid #fca5a5; /* Red 300 */
    }
    .error[aria-live] {
      display: block;
    }

    /* Progress Indicator */
    .progress {
      display: none;
      text-align: center;
      margin-top: 16px;
    }
    .loader {
      width: 50px; /* Slightly larger loader */
      height: 50px;
      border: 6px solid var(--surface);
      border-top-color: var(--primary);
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 12px; /* Adjusted margin */
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    .progress p {
      font-size: 1.1rem;
      font-weight: 500;
    }

    /* Result Section */
    .result {
      display: none;
      text-align: center;
      background: rgba(230,246,255,0.6); /* Light blue with transparency */
      backdrop-filter: blur(8px); /* Stronger blur */
      padding: 32px; /* Increased padding */
      border-radius: var(--radius);
      border: 1px solid rgba(90,103,216,0.1); /* Subtle border */
      box-shadow: 0 8px 30px rgba(0,0,0,0.05);
      margin-top: -16px; /* Overlap with previous section */
      position: relative;
      z-index: 1;
    }
    .result h3 {
      font-size: 1.6rem;
      color: var(--primary);
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }
    .qr-preview {
      width: 240px; /* Slightly larger preview */
      height: 240px;
      margin: 0 auto 24px;
      border-radius: var(--radius);
      box-shadow: 0 6px 20px rgba(0,0,0,0.15); /* More prominent shadow */
      object-fit: contain; /* Ensure image scales correctly */
      background-color: #fff; /* White background for QR code */
      padding: 5px; /* Small padding if QR code is tight to edge */
    }
    .result-links {
      display: flex;
      gap: 16px;
      justify-content: center;
      flex-wrap: wrap;
    }
    .result-links .btn {
      min-width: 160px; /* Ensure buttons have minimum width */
    }

    /* Features Section */
    .features {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); /* Adjusted min-width for better mobile fit */
      gap: 24px;
    }
    .feature {
      background: var(--surface);
      border-radius: var(--radius);
      padding: 20px; /* Slightly more padding */
      text-align: center;
      box-shadow: 0 6px 18px rgba(0,0,0,0.05);
      transition: transform var(--transition), box-shadow var(--transition);
      border: 1px solid rgba(0,0,0,0.05); /* Subtle border */
    }
    .feature:hover {
      transform: translateY(-5px); /* More lift */
      box-shadow: var(--shadow-hover);
    }
    .feature svg {
      width: 40px; /* Larger icons */
      height: 40px;
      margin-bottom: 12px;
      fill: var(--primary);
      transition: fill var(--transition);
    }
    .feature:hover svg {
      fill: var(--accent);
    }
    .feature h4 {
      font-size: 1.1rem;
      font-weight: 600;
    }

    /* Responsive Adjustments */
    @media (max-width: 600px) {
      body {
        padding: 15px;
      }
      header {
        flex-direction: column;
        gap: 16px;
        padding: 20px;
      }
      header h1 {
        font-size: 1.5rem;
      }
      main {
        padding: 20px;
        gap: 24px;
      }
      .upload-zone {
        padding: 30px;
      }
      .upload-zone span {
        font-size: 1rem;
      }
      .result h3 {
        font-size: 1.4rem;
      }
      .qr-preview {
        width: 200px;
        height: 200px;
      }
      .result-links .btn {
        flex: 1 1 100%; /* Stack buttons on small screens */
      }
      .features {
        grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); /* Even smaller cards for tiny screens */
      }
      .feature {
        padding: 15px;
      }
    }
  </style>
</head>
<body data-theme="light">
  <div class="container">
    <header>
      <h1>QR Image Platform</h1>
      <button class="theme-toggle" aria-label="Basculer thème sombre/clair" id="themeToggle">
        <svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
        <svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </button>
    </header>
    <main>
      <div class="upload-zone" id="uploadZone">
        <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7z"/><path d="M5 18v2h14v-2H5z"/></svg>
        <span>Cliquez ou glissez-déposez votre image (<strong>Max 10 MB</strong>)</span>
        <button class="btn" id="selectFileBtn">Choisir un fichier</button>
      </div>
      <input type="file" id="imageFile" class="file-input" accept="image/*" aria-label="Sélecteur d’image">
      <div class="error" id="errorMsg" role="alert" aria-live="assertive"></div>
      <div class="progress" id="progress">
        <div class="loader" aria-hidden="true"></div>
        <p>Traitement en cours...</p>
      </div>
      <div class="result" id="result">
        <h3>✅ QR Code généré !</h3>
        <img id="qrPreview" class="qr-preview" alt="QR Code généré">
        <div class="result-links">
          <a id="viewLink" class="btn" target="_blank">Voir l’image</a>
          <a id="downloadQrLink" class="btn" download>Télécharger QR</a>
        </div>
      </div>
      <div class="features">
        <div class="feature">
          <svg viewBox="0 0 24 24"><path d="M12 2a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0V3a1 1 0 0 1 1-1zm5.657 3.343a1 1 0 0 1 1.414 1.414L18.414 7.07a1 1 0 1 1-1.414-1.414l1.657-1.657zM21 11h-2a1 1 0 0 1 0-2h2a1 1 0 1 1 0 2zm-3.343 5.657a1 1 0 0 1-1.414 1.414L15.07 16.414a1 1 0 1 1 1.414-1.414l1.171 1.171zM13 21a1 1 0 0 1-2 0v-2a1 1 0 1 1 2 0v2zm-5.657-3.343a1 1 0 0 1-1.414-1.414L5.586 15.07a1 1 0 0 1 1.414 1.414l1.343 1.343zM3 13H1a1 1 0 1 1 0-2h2a1 1 0 0 1 0 2zm3.343-5.657a1 1 0 1 1 1.414-1.414L8.414 5.586a1 1 0 1 1-1.414 1.414L6.343 7.343z"/></svg>
          <h4>Accessible Partout</h4>
        </div>
        <div class="feature">
          <svg viewBox="0 0 24 24"><path d="M17 1H7C5.9 1 5 1.9 5 3v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-2-2-2zm-2 20H9v-1h6v1zm3-3V6c0-1.1-.9-2-2-2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2z"/></svg>
          <h4>Mobile-Friendly</h4>
        </div>
        <div class="feature">
          <svg viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.5 3.8 10.7 9 12 5.2-1.3 9-6.5 9-12V5l-9-4zM12 21.6c-4.3-1.2-7.5-5.3-7.5-10.6V6.1l7.5-3.3 7.5 3.3v4.9c0 5.3-3.2 9.4-7.5 10.6zM11 15h2v2h-2zm0-8h2v6h-2z"/></svg>
          <h4>Sécurisé</h4>
        </div>
        <div class="feature">
          <svg viewBox="0 0 24 24"><path d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.51 0-2.91-.49-4.08-1.31L7.1 18.34c1.42.98 3.16 1.66 5.05 1.66 4.97 0 9-4.03 9-9s-4.03-9-9-9z"/></svg>
          <h4>Ultra-Rapide</h4>
        </div>
      </div>
    </main>
  </div>

  <script>
    // Theme toggle
    const body = document.body;
    const themeToggle = document.getElementById('themeToggle');

    themeToggle.addEventListener('click', () => {
      body.dataset.theme = body.dataset.theme === 'dark' ? 'light' : 'dark';
      // Store user's preference
      localStorage.setItem('theme', body.dataset.theme);
    });

    // Apply saved theme on load
    document.addEventListener('DOMContentLoaded', () => {
      const savedTheme = localStorage.getItem('theme') || 'light';
      body.dataset.theme = savedTheme;
    });

    const uploadZone = document.getElementById('uploadZone');
    const fileInput  = document.getElementById('imageFile');
    const selectFileBtn = document.getElementById('selectFileBtn'); // Le nouveau bouton que vous avez ajouté
    const errorMsg   = document.getElementById('errorMsg');
    const progress   = document.getElementById('progress');
    const result     = document.getElementById('result');

    // C'EST ICI QUE SE TROUVE LA MODIFICATION CLÉ POUR LE MOBILE
    // Le clic sur le bouton 'Choisir un fichier' déclenche l'input de fichier.
    selectFileBtn.addEventListener('click', (e) => {
      e.preventDefault(); // Empêche le comportement par défaut du bouton (ex: soumission de formulaire)
      fileInput.click();  // Déclenche le clic programmatique sur l'input de fichier caché
    });

    // Fonctionnalité de glisser-déposer pour la zone d'upload
    ['dragover','dragleave','drop'].forEach(e => {
      uploadZone.addEventListener(e, ev => {
        ev.preventDefault(); // Empêche le comportement par défaut du navigateur (ex: ouvrir le fichier)
        ev.stopPropagation(); // Arrête la propagation pour ne pas affecter les éléments parents
        if (e === 'dragover') {
          uploadZone.classList.add('dragover');
        } else if (e === 'dragleave') {
          uploadZone.classList.remove('dragover');
        }
      });
    });

    uploadZone.addEventListener('drop', e => {
      uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
      }
    });

    // Gère la sélection de fichier via le changement d'input (c'est là que le fichier est réellement traité)
    fileInput.addEventListener('change', e => {
      // AJOUTEZ CETTE VÉRIFICATION pour vous assurer qu'un fichier a bien été sélectionné
      if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
      }
    });

    // ... (vos fonctions showError, hideError, handleFile restent les mêmes,
    // MAIS assurez-vous que `handleFile` a bien le `if (!file)` au début comme suggéré précédemment) ...

    // Début de la fonction handleFile (juste pour référence, le corps reste le même)
    async function handleFile(file) {
      hideError();
      if (!file) { // Vérification supplémentaire au cas où le fichier est nul
          return showError('Aucun fichier sélectionné ou une erreur s\'est produite.');
      }

    function showError(msg) {
      errorMsg.textContent = msg;
      errorMsg.style.display = 'block';
      errorMsg.setAttribute('aria-live', 'assertive'); // Make screen readers announce it
      progress.style.display = result.style.display = 'none';
      result.setAttribute('aria-hidden', 'true');
      progress.setAttribute('aria-hidden', 'true');
    }

    function hideError() {
      errorMsg.style.display = 'none';
      errorMsg.removeAttribute('aria-live');
    }

    async function handleFile(file) {
      hideError();
      if (!file.type.startsWith('image/')) {
        return showError('Fichier non supporté. Veuillez sélectionner une image.');
      }
      if (file.size > 10 * 1024 * 1024) { // 10MB
        return showError('Le fichier est trop volumineux. La taille maximale est de 10 MB.');
      }

      progress.style.display = 'block';
      progress.setAttribute('aria-hidden', 'false');
      result.style.display = 'none';
      result.setAttribute('aria-hidden', 'true');


      const form = new FormData();
      form.append('image', file);

      try {
        const response = await fetch('/upload', {
          method: 'POST',
          body: form,
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || `Erreur serveur: ${response.status}`);
        }

        const data = await response.json();

        progress.style.display = 'none';
        progress.setAttribute('aria-hidden', 'true');

        if (data.success) {
          document.getElementById('qrPreview').src = data.qr_url;
          document.getElementById('qrPreview').alt = `QR Code pour ${file.name}`;
          document.getElementById('viewLink').href = data.view_url;
          document.getElementById('downloadQrLink').href = data.download_qr_url;
          result.style.display = 'block';
          result.setAttribute('aria-hidden', 'false');
        } else {
          showError(data.error || 'Une erreur inconnue est survenue.');
        }
      } catch (error) {
        console.error('Upload error:', error);
        showError(`Erreur lors du téléchargement : ${error.message || 'Problème réseau ou serveur indisponible.'}`);
      }
    }
  </script>
</body>
</html>
'''

    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_html)

    # Template de visualisation
    view_html = '''<!DOCTYPE html>
<html lang="fr" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Image partagée</title>
  <style>
    /* Base CSS from index.html for consistent themes */
    :root {
      --bg: #f0f2f5;
      --surface: #fff;
      --text: #333;
      --primary: #5a67d8;
      --primary-dark: #4c52af;
      --accent: #ed64a6;
      --radius: 12px;
      --transition: 0.3s ease;
      --shadow-light: 0 12px 40px rgba(0,0,0,0.08);
      --shadow-hover: 0 16px 48px rgba(0,0,0,0.12);
    }
    [data-theme="dark"] {
      --bg: #1a202c;
      --surface: #2d3748;
      --text: #e2e8f0;
      --primary: #667eea;
      --primary-dark: #556be7;
      --accent: #f687b3;
      --shadow-light: 0 12px 40px rgba(0,0,0,0.2);
      --shadow-hover: 0 16px 48px rgba(0,0,0,0.3);
    }

    /* General Reset */
    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh; /* Use min-height for full viewport height */
      padding: 20px; /* Add padding for smaller screens */
      transition: background var(--transition), color var(--transition);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    /* Card Styling */
    .card {
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: var(--shadow-light);
      overflow: hidden;
      max-width: 600px;
      width: 100%;
      transition: background var(--transition), box-shadow var(--transition);
      display: flex;
      flex-direction: column;
      align-items: center; /* Center content horizontally */
    }
    .card header {
      background: var(--primary);
      color: #fff;
      padding: 24px;
      text-align: center;
      width: 100%; /* Ensure header spans full width */
    }
    .card header h2 {
      font-size: 1.8rem;
      font-weight: 700;
    }
    .card .content {
      padding: 32px; /* Increased padding */
      text-align: center;
      display: flex;
      flex-direction: column;
      gap: 24px; /* More space between elements */
      width: 100%;
    }
    .card img {
      max-width: 100%;
      height: auto; /* Maintain aspect ratio */
      border-radius: var(--radius);
      box-shadow: 0 8px 25px rgba(0,0,0,0.1); /* Stronger shadow */
      margin: 0 auto; /* Center image */
      display: block; /* Remove extra space below image */
    }
    .info {
      font-size: 1rem;
      color: var(--text);
      line-height: 1.6;
    }
    .info p strong {
      color: var(--primary);
    }

    /* Button Styling (reused from index.html for consistency) */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--primary);
      color: #fff;
      padding: 12px 28px;
      border: none;
      border-radius: var(--radius);
      cursor: pointer;
      text-decoration: none;
      font-weight: 600;
      transition: transform var(--transition), box-shadow var(--transition), background-color var(--transition);
    }
    .btn:hover {
      transform: translateY(-3px);
      background-color: var(--primary-dark);
      box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    .btn:active {
      transform: translateY(0);
      box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .btn:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 3px;
    }

    /* Footer */
    .footer {
      background: rgba(0,0,0,0.03); /* Lighter background */
      text-align: center;
      padding: 18px; /* More padding */
      font-size: .9rem;
      color: var(--text);
      width: 100%;
      border-top: 1px solid rgba(0,0,0,0.05); /* Subtle border */
    }
    .footer a {
      color: var(--primary);
      text-decoration: none;
      font-weight: 600;
      transition: color var(--transition);
    }
    .footer a:hover {
      color: var(--accent);
      text-decoration: underline;
    }

    /* Responsive Adjustments */
    @media (max-width: 600px) {
      body {
        padding: 15px;
      }
      .card header {
        padding: 20px;
      }
      .card header h2 {
        font-size: 1.5rem;
      }
      .card .content {
        padding: 20px;
        gap: 18px;
      }
      .info {
        font-size: 0.9rem;
      }
      .btn {
        padding: 10px 20px;
        font-size: 0.95rem;
      }
      .footer {
        padding: 14px;
        font-size: 0.8rem;
      }
    }
  </style>
</head>
<body>
  <div class="card">
    <header><h2>Image Partagée</h2></header>
    <div class="content">
      <img src="{{ url_for('serve_image', image_id=image_id) }}" alt="Image partagée: {{ image_info.original_name }}">
      <div class="info">
        <p><strong>Nom :</strong> {{ image_info.original_name }}</p>
        <p><strong>Upload :</strong> {{ image_info.upload_time[:10] }}</p>
      </div>
      <a href="{{ url_for('serve_image', image_id=image_id) }}" class="btn" download="{{ image_info.original_name }}">⬇️ Télécharger</a>
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
