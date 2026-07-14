import os
import uuid
import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
import qrcode
from qrcode.image.pil import PilImage

from config import Config

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(BACKEND_DIR, '..', 'frontend', 'templates'))
STATIC_DIR = os.path.abspath(os.path.join(BACKEND_DIR, '..', 'frontend', 'static'))

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.config.from_object(Config)

db = SQLAlchemy(app)

# --- DATABASE MODELS ---

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Certificate(db.Model):
    __tablename__ = 'certificates'
    # Unique Certificate ID (e.g. CERT-2026-XXXX)
    id = db.Column(db.String(50), primary_key=True)
    recipient_name = db.Column(db.String(150), nullable=False)
    certificate_title = db.Column(db.String(200), nullable=False)
    course_name = db.Column(db.String(200), nullable=False)
    grade = db.Column(db.String(50), nullable=True)
    issue_date = db.Column(db.Date, nullable=False, default=datetime.date.today)
    expiry_date = db.Column(db.Date, nullable=True)
    signature = db.Column(db.Text, nullable=False) # Cryptographic signature in Hex format
    status = db.Column(db.String(20), nullable=False, default='Active') # 'Active' or 'Revoked'
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))

    def to_canonical_string(self):
        # Deterministic representation for hashing
        expiry_str = self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else 'None'
        grade_str = self.grade if self.grade else 'None'
        return f"{self.id}|{self.recipient_name}|{self.certificate_title}|{self.course_name}|{grade_str}|{self.issue_date.strftime('%Y-%m-%d')}|{expiry_str}"

# --- CRYPTOGRAPHY HELPERS ---

def init_keys():
    """Generates RSA key pair if not exists."""
    private_path = app.config['PRIVATE_KEY_PATH']
    public_path = app.config['PUBLIC_KEY_PATH']
    
    if not os.path.exists(private_path) or not os.path.exists(public_path):
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        # Save private key
        with open(private_path, 'wb') as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # Save public key
        public_key = private_key.public_key()
        with open(public_path, 'wb') as f:
            f.write(public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))

def get_private_key():
    with open(app.config['PRIVATE_KEY_PATH'], 'rb') as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def get_public_key():
    with open(app.config['PUBLIC_KEY_PATH'], 'rb') as f:
        return serialization.load_pem_public_key(f.read())

def sign_data(data_str: str) -> str:
    private_key = get_private_key()
    signature = private_key.sign(
        data_str.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return signature.hex()

def verify_signature(data_str: str, signature_hex: str) -> bool:
    try:
        public_key = get_public_key()
        signature = bytes.fromhex(signature_hex)
        public_key.verify(
            signature,
            data_str.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        app.logger.error(f"Signature verification failed: {e}")
        return False

# --- QR CODE GENERATION ---

def generate_qr_code(cert_id: str):
    # Determine the URL pointing to the verification page
    # Since we don't know the exact domain at runtime, we construct a path URL
    # or rely on the host of the request, but we can generate a absolute URL by configuration or default.
    # For local/testing we can use the default request host, but for generating the image,
    # we link to: http://<host>/verify/<cert_id>
    # To support this dynamically, we can use a placeholder or relative path, but normal QR readers need absolute URLs.
    # We will use /verify/<cert_id> which resolves relative or standard local host configuration.
    
    # We will generate QR codes that point to the verification page on the system.
    # In standard setup we use the request host. If not available we fall back to http://127.0.0.1:5000
    host = request.host_url if request else "http://127.0.0.1:5000/"
    url = f"{host}verify/{cert_id}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Standard QR code formatting with white background for maximum contrast and readability across all devices and scanner libraries
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff") # Dark Slate on White
    
    qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{cert_id}.png")
    img.save(qr_path)
    return f"uploads/{cert_id}.png"

# --- DECORATORS & MIDDLEWARE ---

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin_logged_in' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_logged_in'] = True
            session['admin_username'] = admin.username
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Successfully logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
def dashboard():
    certs = Certificate.query.order_by(Certificate.created_at.desc()).all()
    
    # Calculate statistics
    total_issued = len(certs)
    active_count = sum(1 for c in certs if c.status == 'Active')
    revoked_count = total_issued - active_count
    
    return render_template('dashboard.html', 
                           certificates=certs, 
                           total_issued=total_issued,
                           active_count=active_count,
                           revoked_count=revoked_count)

@app.route('/admin/issue', methods=['GET', 'POST'])
@login_required
def issue_certificate():
    if request.method == 'POST':
        recipient_name = request.form.get('recipient_name')
        certificate_title = request.form.get('certificate_title')
        course_name = request.form.get('course_name')
        grade = request.form.get('grade') or None
        
        issue_date_str = request.form.get('issue_date')
        expiry_date_str = request.form.get('expiry_date') or None
        
        # Convert strings to dates
        try:
            issue_date = datetime.datetime.strptime(issue_date_str, '%Y-%m-%d').date() if issue_date_str else datetime.date.today()
            expiry_date = datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            return render_template('issue.html')

        # Generate custom unique Certificate ID
        unique_suffix = uuid.uuid4().hex[:6].upper()
        cert_id = f"CERT-{datetime.date.today().year}-{unique_suffix}"
        
        # Create temp certificate model to compute canonical string
        temp_cert = Certificate(
            id=cert_id,
            recipient_name=recipient_name,
            certificate_title=certificate_title,
            course_name=course_name,
            grade=grade,
            issue_date=issue_date,
            expiry_date=expiry_date
        )
        
        # Sign the canonical certificate data
        canonical_data = temp_cert.to_canonical_string()
        signature = sign_data(canonical_data)
        temp_cert.signature = signature
        
        # Add to database
        db.session.add(temp_cert)
        db.session.commit()
        
        # Generate QR code pointing to this URL
        generate_qr_code(cert_id)
        
        flash(f'Certificate {cert_id} successfully issued!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('issue.html')

@app.route('/admin/revoke/<cert_id>', methods=['POST'])
@login_required
def revoke_certificate(cert_id):
    cert = db.get_or_404(Certificate, cert_id)
    cert.status = 'Revoked'
    db.session.commit()
    flash(f'Certificate {cert_id} has been revoked.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/verify', methods=['GET', 'POST'])
def verify_manual():
    # Helper endpoint to handle manual ID inputs or query parameters
    cert_id = request.args.get('cert_id') or request.form.get('cert_id')
    if cert_id:
        return redirect(url_for('verify', cert_id=cert_id.strip()))
    flash('Please enter a valid certificate ID.', 'warning')
    return redirect(url_for('index'))

@app.route('/verify/<cert_id>')
def verify(cert_id):
    cert = db.session.get(Certificate, cert_id)
    
    if not cert:
        return render_template('verify.html', status='not_found', cert_id=cert_id)
    
    # Cryptographically verify the certificate data
    canonical_data = cert.to_canonical_string()
    is_valid_sig = verify_signature(canonical_data, cert.signature)
    
    if not is_valid_sig:
        return render_template('verify.html', status='tampered', certificate=cert)
        
    if cert.status == 'Revoked':
        return render_template('verify.html', status='revoked', certificate=cert)
        
    # Check if expired
    if cert.expiry_date and cert.expiry_date < datetime.date.today():
        return render_template('verify.html', status='expired', certificate=cert)
        
    return render_template('verify.html', status='valid', certificate=cert)

@app.route('/certificate/<cert_id>')
def view_certificate(cert_id):
    cert = db.get_or_404(Certificate, cert_id)
    
    # Cryptographically verify signature
    canonical_data = cert.to_canonical_string()
    is_valid_sig = verify_signature(canonical_data, cert.signature)
    
    if not is_valid_sig or cert.status != 'Active':
        return redirect(url_for('verify', cert_id=cert_id))
        
    # Also check if expired
    if cert.expiry_date and cert.expiry_date < datetime.date.today():
        return redirect(url_for('verify', cert_id=cert_id))
        
    # QR code path (generate if missing)
    qr_filename = f"{cert_id}.png"
    qr_path = os.path.join(app.config['UPLOAD_FOLDER'], qr_filename)
    if not os.path.exists(qr_path):
        generate_qr_code(cert_id)
        
    return render_template('view_certificate.html', certificate=cert, qr_image=url_for('static', filename=f'uploads/{qr_filename}'))

@app.route('/api/verify/<cert_id>')
def api_verify(cert_id):
    # JSON endpoint for API based verification (e.g. mobile apps or offline verifiers)
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return jsonify({'status': 'not_found', 'message': 'Certificate not found'}), 404
        
    canonical_data = cert.to_canonical_string()
    is_valid_sig = verify_signature(canonical_data, cert.signature)
    
    if not is_valid_sig:
        return jsonify({'status': 'tampered', 'message': 'Cryptographic signature is invalid/tampered'}), 400
        
    return jsonify({
        'id': cert.id,
        'recipient_name': cert.recipient_name,
        'certificate_title': cert.certificate_title,
        'course_name': cert.course_name,
        'grade': cert.grade,
        'issue_date': cert.issue_date.strftime('%Y-%m-%d'),
        'expiry_date': cert.expiry_date.strftime('%Y-%m-%d') if cert.expiry_date else None,
        'status': cert.status,
        'is_signature_valid': is_valid_sig
    })

# --- APPLICATION INITIALIZATION ---

def seed_admin():
    db.create_all()
    # Check if admin user exists, if not seed one
    admin = Admin.query.filter_by(username='admin').first()
    if not admin:
        hashed_password = generate_password_hash('admin123')
        default_admin = Admin(username='admin', password_hash=hashed_password)
        db.session.add(default_admin)
        db.session.commit()
        app.logger.info("Default administrator seeded: username='admin', password='admin123'")

def regenerate_all_qr_codes():
    try:
        certs = Certificate.query.all()
        for cert in certs:
            generate_qr_code(cert.id)
        app.logger.info("All certificate QR codes regenerated with high-contrast formatting.")
    except Exception as e:
        app.logger.error(f"Failed to regenerate QR codes: {e}")

with app.app_context():
    init_keys()
    seed_admin()
    regenerate_all_qr_codes()

if __name__ == '__main__':
    app.run(debug=True)
