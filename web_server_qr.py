#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur web pour partager des images via QR code
Alternative qui héberge l'image sur un serveur local
"""

from flask import Flask, send_file, render_template_string, request
import qrcode
import os
import socket
import threading
import time
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Créer le dossier uploads s'il n'existe pas
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Stockage des images avec des IDs uniques
image_storage = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image partagée</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
            background: #f0f0f0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            max-width: 90%;
            text-align: center;
        }
        img {
            max-width: 100%;
            max-height: 80vh;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .info {
            margin-top: 15px;
            color: #666;
            font-size: 14px;
        }
        .download-btn {
            display: inline-block;
            margin-top: 15px;
            padding: 10px 20px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: background 0.3s;
        }
        .download-btn:hover {
            background: #0056b3;
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Image partagée via QR Code</h2>
        <img src="/image/{{ image_id }}" alt="Image partagée">
        <div class="info">
            <p>Image partagée le {{ timestamp }}</p>
            <a href="/image/{{ image_id }}?download=1" class="download-btn">Télécharger l'image</a>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return """
    <h1>Serveur de partage d'images QR</h1>
    <p>Ce serveur permet de partager des images via des codes QR.</p>
    <p>Utilisez le script Python pour générer un QR code pointant vers ce serveur.</p>
    """

@app.route('/view/<image_id>')
def view_image(image_id):
    if image_id not in image_storage:
        return "Image non trouvée", 404
    
    image_info = image_storage[image_id]
    return render_template_string(HTML_TEMPLATE, 
                                image_id=image_id,
                                timestamp=image_info['timestamp'])

@app.route('/image/<image_id>')
def serve_image(image_id):
    if image_id not in image_storage:
        return "Image non trouvée", 404
    
    image_info = image_storage[image_id]
    file_path = image_info['path']
    
    if not os.path.exists(file_path):
        return "Fichier image non trouvé", 404
    
    # Si le paramètre download est présent, forcer le téléchargement
    if request.args.get('download'):
        return send_file(file_path, as_attachment=True, 
                        download_name=image_info['original_name'])
    
    return send_file(file_path)

def get_local_ip():
    """Obtient l'adresse IP locale"""
    try:
        # Créer une socket pour obtenir l'IP locale
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def create_qr_for_server(image_path, server_url, output_path="server_qr.png"):
    """
    Crée un QR code pointant vers le serveur web
    """
    try:
        # Générer un ID unique pour l'image
        image_id = str(uuid.uuid4())
        
        # Stocker les informations de l'image
        image_storage[image_id] = {
            'path': os.path.abspath(image_path),
            'original_name': os.path.basename(image_path),
            'timestamp': time.strftime('%d/%m/%Y à %H:%M')
        }
        
        # URL complète vers l'image
        full_url = f"{server_url}/view/{image_id}"
        
        # Créer le QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        qr.add_data(full_url)
        qr.make(fit=True)
        
        qr_image = qr.make_image(fill_color="black", back_color="white")
        qr_image.save(output_path)
        
        print(f"✅ QR Code créé: {output_path}")
        print(f"🔗 URL: {full_url}")
        print(f"📱 Scannez le QR code pour voir l'image sur n'importe quel appareil")
        
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création du QR code: {e}")
        return False

def start_server(port=5000):
    """Démarre le serveur Flask"""
    app.run(host='0.0.0.0', port=port, debug=False)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Serveur web pour partage d\'images via QR')
    parser.add_argument('image_path', nargs='?', help='Chemin vers l\'image à partager')
    parser.add_argument('-p', '--port', type=int, default=5000, help='Port du serveur (défaut: 5000)')
    parser.add_argument('-o', '--output', default='server_qr.png', help='Nom du fichier QR code')
    parser.add_argument('--server-only', action='store_true', help='Démarrer seulement le serveur')
    
    args = parser.parse_args()
    
    # Obtenir l'IP locale
    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:{args.port}"
    
    if args.server_only:
        print(f"🚀 Démarrage du serveur sur {server_url}")
        print("📱 Utilisez un autre script pour créer des QR codes pointant vers ce serveur")
        start_server(args.port)
        return
    
    if not args.image_path:
        print("Erreur: Veuillez spécifier le chemin de l'image")
        return
    
    if not os.path.exists(args.image_path):
        print(f"Erreur: Le fichier {args.image_path} n'existe pas")
        return
    
    print(f"🚀 Démarrage du serveur sur {server_url}")
    print(f"📸 Préparation du partage de: {args.image_path}")
    
    # Créer le QR code
    create_qr_for_server(args.image_path, server_url, args.output)
    
    # Démarrer le serveur dans un thread séparé
    server_thread = threading.Thread(target=start_server, args=(args.port,))
    server_thread.daemon = True
    server_thread.start()
    
    print(f"\n✅ Serveur démarré avec succès!")
    print(f"🔗 Accès local: http://localhost:{args.port}")
    print(f"🌐 Accès réseau: {server_url}")
    print(f"📱 QR Code sauvegardé: {args.output}")
    print("\n💡 Instructions:")
    print("1. Scannez le QR code avec n'importe quel smartphone")
    print("2. L'image s'affichera automatiquement dans le navigateur")
    print("3. Possibilité de télécharger l'image depuis le navigateur")
    print("\n⚠️  Gardez ce programme ouvert pour que le serveur reste actif")
    print("   Appuyez sur Ctrl+C pour arrêter le serveur")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du serveur...")

if __name__ == "__main__":
    main()

# Exemples d'utilisation:
# python web_server_qr.py mon_image.jpg
# python web_server_qr.py mon_image.jpg --port 8080
# python web_server_qr.py --server-only --port 5000