import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-antigravity-12345-very-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 
        'postgresql://postgres:qZF.LVxF%3F5b98yg@db.jrnybkvkyehvsqlueiij.supabase.co:5432/postgres'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Cryptographic keys location
    KEYS_DIR = os.path.abspath(os.path.join(BASE_DIR, 'keys'))
    PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, 'private_key.pem')
    PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, 'public_key.pem')
    
    # Upload folder for generated QR codes
    UPLOAD_FOLDER = os.path.abspath(os.path.join(BASE_DIR, '..', 'frontend', 'static', 'uploads'))
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(KEYS_DIR, exist_ok=True)
