document.addEventListener('DOMContentLoaded', () => {
    // --- FLASH MESSAGE FADE OUT ---
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 600);
        }, 5000);
    });

    // --- DASHBOARD SEARCH FILTER ---
    const searchInput = document.getElementById('search-cert');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const rows = document.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const certId = row.querySelector('.cert-id-col').textContent.toLowerCase();
                const recipient = row.querySelector('.recipient-col').textContent.toLowerCase();
                const title = row.querySelector('.title-col').textContent.toLowerCase();
                
                if (certId.includes(query) || recipient.includes(query) || title.includes(query)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    }

    // --- COPY SHARE LINK ---
    const copyBtn = document.getElementById('btn-copy-link');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const url = copyBtn.dataset.url;
            navigator.clipboard.writeText(url).then(() => {
                const originalText = copyBtn.innerHTML;
                copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                copyBtn.style.background = '#10b981';
                copyBtn.style.color = '#fff';
                
                setTimeout(() => {
                    copyBtn.innerHTML = originalText;
                    copyBtn.style.background = '';
                    copyBtn.style.color = '';
                }, 2000);
            }).catch(err => {
                console.error('Could not copy text: ', err);
            });
        });
    }

    // --- QR CODE SCANNER (html5-qrcode library integration) ---
    const startScannerBtn = document.getElementById('start-scanner-btn');
    const stopScannerBtn = document.getElementById('stop-scanner-btn');
    const qrPlaceholder = document.getElementById('scanner-placeholder');
    const readerDiv = document.getElementById('reader');
    const fileInput = document.getElementById('qr-file-input');

    let html5QrCode = null;
    
    // Normalize decoded text (URL or ID) and redirect safely
    function handleDecodedText(decodedText) {
        const text = decodedText.trim();
        if (text.includes('/verify/')) {
            const parts = text.split('/verify/');
            const certId = parts[parts.length - 1].split('?')[0]; // Strip query parameters
            window.location.href = `/verify/${encodeURIComponent(certId)}`;
        } else if (text.startsWith('http://') || text.startsWith('https://')) {
            window.location.href = text;
        } else {
            window.location.href = `/verify/${encodeURIComponent(text)}`;
        }
    }

    // Helper to get or create scanner instance
    function getScannerInstance() {
        if (!html5QrCode) {
            html5QrCode = new Html5Qrcode("reader");
        }
        return html5QrCode;
    }

    if (startScannerBtn) {
        startScannerBtn.addEventListener('click', () => {
            // Show scanning UI
            qrPlaceholder.style.display = 'none';
            readerDiv.style.display = 'block';
            startScannerBtn.style.display = 'none';
            stopScannerBtn.style.display = 'inline-flex';
            document.querySelector('.qr-scanner-section').classList.add('scanning');

            const scanner = getScannerInstance();

            scanner.start(
                { facingMode: "environment" },
                {
                    fps: 10,
                    qrbox: { width: 250, height: 250 }
                },
                (decodedText) => {
                    // Success callback
                    scanner.stop().then(() => {
                        handleDecodedText(decodedText);
                    }).catch(err => {
                        console.error("Failed to stop camera after scan", err);
                    });
                },
                (errorMessage) => {
                    // Keep scanning
                }
            ).catch(err => {
                console.error("Unable to start scanning", err);
                alert("Failed to access camera. Please check permissions.");
                // Reset UI
                qrPlaceholder.style.display = 'flex';
                readerDiv.style.display = 'none';
                startScannerBtn.style.display = 'inline-flex';
                stopScannerBtn.style.display = 'none';
                document.querySelector('.qr-scanner-section').classList.remove('scanning');
            });
        });
    }

    if (stopScannerBtn) {
        stopScannerBtn.addEventListener('click', () => {
            if (html5QrCode && html5QrCode.isScanning) {
                html5QrCode.stop().then(() => {
                    qrPlaceholder.style.display = 'flex';
                    readerDiv.style.display = 'none';
                    startScannerBtn.style.display = 'inline-flex';
                    stopScannerBtn.style.display = 'none';
                    document.querySelector('.qr-scanner-section').classList.remove('scanning');
                }).catch(err => {
                    console.error("Error stopping camera", err);
                });
            } else {
                qrPlaceholder.style.display = 'flex';
                readerDiv.style.display = 'none';
                startScannerBtn.style.display = 'inline-flex';
                stopScannerBtn.style.display = 'none';
                document.querySelector('.qr-scanner-section').classList.remove('scanning');
            }
        });
    }

    // --- QR FILE UPLOAD SCANNER ---
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length === 0) {
                return;
            }
            const imageFile = e.target.files[0];
            
            // Stop the camera scanner if active
            const scanPromise = (html5QrCode && html5QrCode.isScanning)
                ? html5QrCode.stop()
                : Promise.resolve();

            scanPromise.then(() => {
                if (stopScannerBtn && stopScannerBtn.style.display !== 'none') {
                    qrPlaceholder.style.display = 'flex';
                    readerDiv.style.display = 'none';
                    startScannerBtn.style.display = 'inline-flex';
                    stopScannerBtn.style.display = 'none';
                    document.querySelector('.qr-scanner-section').classList.remove('scanning');
                }

                // Decode file using jsQR
                const reader = new FileReader();
                reader.onload = function(event) {
                    const img = new Image();
                    img.onload = function() {
                        const canvas = document.createElement('canvas');
                        const context = canvas.getContext('2d');
                        canvas.width = img.width;
                        canvas.height = img.height;
                        context.drawImage(img, 0, 0);
                        
                        const imageData = context.getImageData(0, 0, img.width, img.height);
                        
                        // Try standard detection first
                        let code = jsQR(imageData.data, imageData.width, imageData.height, {
                            inversionAttempts: "dontInvert",
                        });
                        
                        // If standard fails, try both normal/inverted (essential for dark theme screenshots/inverted codes)
                        if (!code) {
                            code = jsQR(imageData.data, imageData.width, imageData.height, {
                                inversionAttempts: "attemptBoth",
                            });
                        }
                        
                        if (code) {
                            handleDecodedText(code.data);
                        } else {
                            console.error("jsQR: No QR code found in image.");
                            alert("Verification Failed: No clear QR code found in the uploaded image. Please try a clearer image.");
                            fileInput.value = "";
                        }
                    };
                    img.onerror = function() {
                        alert("Error loading the image file.");
                        fileInput.value = "";
                    };
                    img.src = event.target.result;
                };
                reader.onerror = function() {
                    alert("Error reading file.");
                    fileInput.value = "";
                };
                reader.readAsDataURL(imageFile);
            }).catch(err => {
                console.error("Error stopping live scanner:", err);
            });
        });
    }
});
