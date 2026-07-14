import os
# Force in-memory database URI for test environment before importing app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import unittest
import datetime
from flask import session
from app import app, db, Admin, Certificate, init_keys, sign_data, verify_signature, seed_admin
from config import Config

class DigitalCertificateVerificationTestCase(unittest.TestCase):
    
    def setUp(self):
        # Override config database URI to use in-memory SQLite database for testing
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app.test_client()
        
        # Build DB schema
        with app.app_context():
            db.create_all()
            # Seed keys & admin
            init_keys()
            seed_admin()
            
    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_key_files_generation(self):
        """Test that RSA keys are created successfully in the keys folder."""
        self.assertTrue(os.path.exists(app.config['PRIVATE_KEY_PATH']))
        self.assertTrue(os.path.exists(app.config['PUBLIC_KEY_PATH']))

    def test_cryptographic_sign_and_verify(self):
        """Test that signing and verification functions work correctly."""
        test_payload = "CERT-2026-TEST|Alice Smith|Certificate of Excellence|Python Programming|A+|2026-06-26|None"
        
        # Generate signature
        with app.app_context():
            signature = sign_data(test_payload)
            self.assertIsNotNone(signature)
            self.assertIsInstance(signature, str)
            
            # Verify signature
            is_valid = verify_signature(test_payload, signature)
            self.assertTrue(is_valid)
            
            # Verify that tampered payload fails verification
            tampered_payload = test_payload.replace("Alice Smith", "Bob Jones")
            is_tampered_invalid = verify_signature(tampered_payload, signature)
            self.assertFalse(is_tampered_invalid)

    def test_index_route(self):
        """Test that public index page loads successfully."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Verify Certificate Authenticity', response.data)

    def test_admin_login_and_logout(self):
        """Test admin login with correct/incorrect credentials and logout."""
        # Test GET login page
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        
        # Test POST incorrect password
        response = self.app.post('/login', data=dict(username='admin', password='wrongpassword'), follow_redirects=True)
        self.assertIn(b'Invalid username or password.', response.data)
        
        # Test POST correct password
        response = self.app.post('/login', data=dict(username='admin', password='admin123'), follow_redirects=True)
        self.assertIn(b'Successfully logged in!', response.data)
        self.assertIn(b'Issuer Dashboard', response.data)
        
        # Test logout
        response = self.app.get('/logout', follow_redirects=True)
        self.assertIn(b'Successfully logged out.', response.data)

    def test_dashboard_access_protection(self):
        """Test that dashboard routes require authentication."""
        # Try accessing dashboard without logging in
        response = self.app.get('/admin/dashboard', follow_redirects=True)
        self.assertIn(b'Please log in to access this page.', response.data)
        
        # Try accessing certificate issuance without logging in
        response = self.app.get('/admin/issue', follow_redirects=True)
        self.assertIn(b'Please log in to access this page.', response.data)

    def test_certificate_issuance_and_verification(self):
        """Test issuing a certificate, checking database storage, and checking verification status."""
        # Log in as admin
        self.app.post('/login', data=dict(username='admin', password='admin123'), follow_redirects=True)
        
        # Issue a certificate
        issue_data = {
            'recipient_name': 'Charlie Brown',
            'certificate_title': 'Outstanding Performance',
            'course_name': 'Ethics in AI',
            'grade': 'Pass',
            'issue_date': '2026-06-26',
            'expiry_date': ''
        }
        
        response = self.app.post('/admin/issue', data=issue_data, follow_redirects=True)
        self.assertIn(b'successfully issued!', response.data)
        
        # Check database
        with app.app_context():
            cert = Certificate.query.filter_by(recipient_name='Charlie Brown').first()
            self.assertIsNotNone(cert)
            self.assertEqual(cert.certificate_title, 'Outstanding Performance')
            self.assertEqual(cert.status, 'Active')
            
            # Verify manually via routes
            response_verify = self.app.get(f'/verify/{cert.id}')
            self.assertEqual(response_verify.status_code, 200)
            self.assertIn(b'Valid & Authentic', response_verify.data)
            self.assertIn(b'Charlie Brown', response_verify.data)
            
            # Verify via API endpoint
            response_api = self.app.get(f'/api/verify/{cert.id}')
            self.assertEqual(response_api.status_code, 200)
            json_data = response_api.get_json()
            self.assertEqual(json_data['status'], 'Active')
            self.assertTrue(json_data['is_signature_valid'])

    def test_certificate_revocation(self):
        """Test revoking an active certificate and checking verification failure."""
        # Log in as admin
        self.app.post('/login', data=dict(username='admin', password='admin123'), follow_redirects=True)
        
        # Issue a certificate
        issue_data = {
            'recipient_name': 'David Miller',
            'certificate_title': 'Specialization Certificate',
            'course_name': 'System Architecture',
            'grade': 'A',
            'issue_date': '2026-06-26',
            'expiry_date': ''
        }
        self.app.post('/admin/issue', data=issue_data, follow_redirects=True)
        
        with app.app_context():
            cert = Certificate.query.filter_by(recipient_name='David Miller').first()
            cert_id = cert.id
            
            # Verify is currently Active and Valid
            response_active = self.app.get(f'/verify/{cert_id}')
            self.assertIn(b'Valid & Authentic', response_active.data)
            
            # Revoke certificate
            response_revoke = self.app.post(f'/admin/revoke/{cert_id}', follow_redirects=True)
            self.assertIn(b'has been revoked.', response_revoke.data)
            
            # Verify status in database
            cert_db = db.session.get(Certificate, cert_id)
            self.assertEqual(cert_db.status, 'Revoked')
            
            # Verify route now displays revoked status
            response_revoked = self.app.get(f'/verify/{cert_id}')
            self.assertIn(b'Revoked Certificate', response_revoked.data)
            
            # Accessing view_certificate redirects to verify
            response_view = self.app.get(f'/certificate/{cert_id}', follow_redirects=True)
            self.assertIn(b'Revoked Certificate', response_view.data)

if __name__ == '__main__':
    unittest.main()
