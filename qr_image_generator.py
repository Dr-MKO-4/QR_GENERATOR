#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de QR Code pour partager des images
Convertit une image en code QR qui permet de la récupérer depuis n'importe quel appareil
"""

import qrcode
import base64
import os
from PIL import Image
import argparse

def image_to_base64(image_path):
    """
    Convertit une image en string base64
    """
    try:
        with open(image_path, "rb") as image_file:
            # Lire le fichier image
            image_data = image_file.read()
            # Convertir en base64
            base64_string = base64.b64encode(image_data).decode('utf-8')
            
            # Déterminer le type MIME basé sur l'extension
            file_extension = os.path.splitext(image_path)[1].lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp'
            }
            
            mime_type = mime_types.get(file_extension, 'image/jpeg')
            
            # Créer l'URL data
            data_url = f"data:{mime_type};base64,{base64_string}"
            
            return data_url
            
    except FileNotFoundError:
        print(f"Erreur: Le fichier {image_path} n'existe pas.")
        return None
    except Exception as e:
        print(f"Erreur lors de la conversion: {e}")
        return None

def create_qr_code(data, output_path="qr_code.png", size=10, border=4):
    """
    Crée un code QR à partir des données
    """
    try:
        # Créer l'objet QR Code
        qr = qrcode.QRCode(
            version=1,  # Taille du QR code (1-40)
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Correction d'erreur
            box_size=size,  # Taille de chaque "pixel"
            border=border,  # Taille de la bordure
        )
        
        # Ajouter les données
        qr.add_data(data)
        qr.make(fit=True)
        
        # Créer l'image
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Sauvegarder
        qr_image.save(output_path)
        print(f"Code QR sauvegardé dans: {output_path}")
        
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création du QR code: {e}")
        return False

def optimize_image(image_path, max_size_kb=100):
    """
    Optimise une image pour réduire sa taille si nécessaire
    """
    try:
        with Image.open(image_path) as img:
            # Vérifier la taille du fichier original
            original_size = os.path.getsize(image_path) / 1024  # en KB
            
            if original_size <= max_size_kb:
                return image_path
            
            # Calculer le ratio de redimensionnement
            ratio = (max_size_kb / original_size) ** 0.5
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            
            # Redimensionner
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Créer un nouveau nom de fichier
            name, ext = os.path.splitext(image_path)
            optimized_path = f"{name}_optimized{ext}"
            
            # Sauvegarder avec compression
            if ext.lower() in ['.jpg', '.jpeg']:
                img_resized.save(optimized_path, "JPEG", quality=85, optimize=True)
            elif ext.lower() == '.png':
                img_resized.save(optimized_path, "PNG", optimize=True)
            else:
                img_resized.save(optimized_path, optimize=True)
            
            print(f"Image optimisée sauvegardée: {optimized_path}")
            print(f"Taille originale: {original_size:.1f} KB")
            print(f"Nouvelle taille: {os.path.getsize(optimized_path)/1024:.1f} KB")
            
            return optimized_path
            
    except Exception as e:
        print(f"Erreur lors de l'optimisation: {e}")
        return image_path

def main():
    parser = argparse.ArgumentParser(description='Convertit une image en code QR')
    parser.add_argument('image_path', help='Chemin vers l\'image à convertir')
    parser.add_argument('-o', '--output', default='qr_code.png', help='Nom du fichier QR code de sortie')
    parser.add_argument('-s', '--size', type=int, default=10, help='Taille des pixels du QR code')
    parser.add_argument('--optimize', action='store_true', help='Optimiser l\'image avant conversion')
    parser.add_argument('--max-size', type=int, default=100, help='Taille maximale en KB pour l\'optimisation')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_path):
        print(f"Erreur: Le fichier {args.image_path} n'existe pas.")
        return
    
    image_path = args.image_path
    
    # Optimiser l'image si demandé
    if args.optimize:
        print("Optimisation de l'image...")
        image_path = optimize_image(image_path, args.max_size)
    
    print(f"Conversion de l'image: {image_path}")
    
    # Convertir l'image en base64
    data_url = image_to_base64(image_path)
    
    if data_url is None:
        return
    
    # Vérifier la taille des données
    data_size = len(data_url)
    print(f"Taille des données: {data_size} caractères")
    
    if data_size > 7000:  # Limite approximative pour les QR codes
        print("⚠️  ATTENTION: Les données sont très volumineuses.")
        print("   Le QR code pourrait être difficile à scanner.")
        print("   Recommandation: utilisez --optimize pour réduire la taille.")
        
        response = input("Continuer quand même? (o/n): ")
        if response.lower() != 'o':
            return
    
    # Créer le QR code
    print("Création du code QR...")
    success = create_qr_code(data_url, args.output, args.size)
    
    if success:
        print("\n✅ Code QR créé avec succès!")
        print(f"📱 Scannez le code QR '{args.output}' avec n'importe quel appareil")
        print("   pour afficher l'image directement dans le navigateur.")
        print("\n💡 Conseils:")
        print("   - Les images plus petites donnent des QR codes plus faciles à scanner")
        print("   - Utilisez --optimize pour réduire automatiquement la taille")
        print("   - Le QR code fonctionne offline une fois scanné")

if __name__ == "__main__":
    main()

# Exemple d'utilisation:
# python qr_image_generator.py mon_image.jpg
# python qr_image_generator.py mon_image.jpg --optimize --output mon_qr.png