#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS P2P File Transfer Application
Tray uygulaması olarak çalışan peer-to-peer dosya paylaşım sistemi
"""

import sys
import os
import socket
import threading
import json
import time
import hashlib
from pathlib import Path
import subprocess
import requests
from io import BytesIO
from flask import Flask, render_template_string, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
import uuid
import platform

# Check and install required packages
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("tkinter not found. Please run: brew install python-tk")
    sys.exit(1)

# tkinterdnd2 import - disable on error
DND_FILES = None
TkinterDnD = tk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    print("Installing tkinterdnd2...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "tkinterdnd2"], check=True)
        # Try import again
        import importlib
        import sys
        if 'tkinterdnd2' in sys.modules:
            importlib.reload(sys.modules['tkinterdnd2'])
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except (subprocess.CalledProcessError, ImportError):
        print("tkinterdnd2 installation failed. Drag & drop feature disabled.")
        DND_FILES = None
        TkinterDnD = tk
except Exception as e:
    print(f"tkinterdnd2 installation error: {e}. Drag & drop feature disabled.")
    DND_FILES = None
    TkinterDnD = tk

try:
    import rumps
except ImportError:
    print("Installing rumps...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "rumps"], check=True)
        # Yeniden import dene
        import importlib
        import sys
        if 'rumps' in sys.modules:
            importlib.reload(sys.modules['rumps'])
        import rumps
    except (subprocess.CalledProcessError, ImportError):
        print("rumps installation failed. Using simple tray menu.")
        rumps = None

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "Pillow"], check=True)
        # Yeniden import dene
        import importlib
        import sys
        if 'PIL' in sys.modules:
            importlib.reload(sys.modules['PIL'])
        from PIL import Image, ImageDraw
    except (subprocess.CalledProcessError, ImportError):
        print("Pillow installation failed. Using simple icon.")
        Image = None
        ImageDraw = None

class P2PFileTransferMac:
    def __init__(self):
        # Hide dock icon (before creating rumps App)
        try:
            import AppKit
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        except:
            pass
            
        if rumps:
            # If rumps is available, run as menu bar application
            self.app = rumps.App("📁", title="P2P Transfer", quit_button=None)
            self.setup_rumps_menu()
        else:
            # If rumps is not available, print IP info to console
            self.app = None
            local_ip = self.get_local_ip()
            print(f"Web Interface Access URLs:")
            print(f"- From other devices: http://{local_ip}:4848")
            print(f"- From this computer: http://127.0.0.1:4848")
        
        self.web_port = 4848
        self.device_name = socket.gethostname()
        self.devices = {}
        self.server_socket = None
        self.discovery_socket = None
        self.running = True
        
        # Web server
        self.flask_app = None
        self.web_server_thread = None
        
        # File management
        self.pending_files = {}  # Pending files
        self.transfer_history = []  # Transfer history
        
        # GUI bileşenleri
        self.root = None
        self.device_listbox = None
        self.progress_var = None
        self.status_label = None
        
        # Start web server
        self.setup_flask_app()
        self.start_web_server_monitor()
        
        # Start services
        self.start_services()
        
        # GUI no longer used, only tray app
    
    def setup_rumps_menu(self):
        """rumps menüsünü kur"""
        if not rumps:
            return
            
        # Create menu items
        local_ip = self.get_local_ip()
        menu_items = [
            rumps.MenuItem(f"Web Arayüzü: http://{local_ip}:4848", callback=None),
            rumps.MenuItem(f"Yerel Erişim: http://127.0.0.1:4848", callback=None),
            rumps.separator,
            rumps.MenuItem("Aç", callback=self.open_window),
            rumps.separator,
            rumps.MenuItem("Çıkış", callback=self.quit_app)
        ]
        
        self.app.menu = menu_items
    
    def setup_flask_app(self):
        """Flask web uygulamasını kur"""
        self.flask_app = Flask(__name__)
        CORS(self.flask_app)
        
        @self.flask_app.route('/')
        def index():
            return render_template_string(self.get_web_interface_html())
        
        @self.flask_app.route('/api/pending_files')
        def get_pending_files():
            return jsonify(list(self.pending_files.values()))
        
        @self.flask_app.route('/api/transfer_history')
        def get_transfer_history():
            return jsonify(self.transfer_history)
        
        @self.flask_app.route('/api/upload', methods=['POST'])
        def upload_file():
            if 'file' not in request.files:
                return jsonify({'error': 'Dosya bulunamadı'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'error': 'Dosya seçilmedi'}), 400
            
            # Save file temporarily
            file_id = str(uuid.uuid4())
            temp_path = os.path.join(os.path.expanduser('~'), 'Desktop', file.filename)
            file.save(temp_path)
            
            # Add to pending files list
            self.pending_files[file_id] = {
                'id': file_id,
                'name': file.filename,
                'path': temp_path,
                'size': os.path.getsize(temp_path),
                'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'pending'
            }
            
            return jsonify({'success': True, 'file_id': file_id})
        
        @self.flask_app.route('/api/download/<file_id>')
        def download_file(file_id):
            if file_id not in self.pending_files:
                return jsonify({'error': 'Dosya bulunamadı'}), 404
            
            file_info = self.pending_files[file_id]
            
            # Add to transfer history
            self.transfer_history.append({
                'file_name': file_info['name'],
                'device': self.device_name,
                'transfer_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'completed'
            })
            
            # Remove from pending files
            del self.pending_files[file_id]
            
            return send_file(file_info['path'], as_attachment=True, download_name=file_info['name'])
        
        @self.flask_app.route('/api/remove/<file_id>', methods=['DELETE'])
        def remove_file(file_id):
            if file_id not in self.pending_files:
                return jsonify({'error': 'Dosya bulunamadı'}), 404
            
            file_info = self.pending_files[file_id]
            # Delete file
            if os.path.exists(file_info['path']):
                os.remove(file_info['path'])
            
            # Bekleyen dosyalardan kaldır
            del self.pending_files[file_id]
            
            return jsonify({'success': True})
    
    def start_web_server_monitor(self):
        """Web sunucusu monitörünü başlat"""
        def monitor_and_start_server():
            while self.running:
                try:
                    # Check port
                    if not self.is_port_in_use(self.web_port):
                        print(f"Port {self.web_port} is free, starting web server...")
                        self.start_web_server()
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    print(f"Web server monitor error: {e}")
                    time.sleep(60)
        
        monitor_thread = threading.Thread(target=monitor_and_start_server, daemon=True)
        monitor_thread.start()
    
    def is_port_in_use(self, port):
        """Portu kontrol et"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result == 0
        except:
            return False
    
    def start_web_server(self):
        """Web sunucusunu başlat"""
        try:
            if self.web_server_thread and self.web_server_thread.is_alive():
                return
            
            def run_server():
                try:
                    self.flask_app.run(host='0.0.0.0', port=self.web_port, debug=False, use_reloader=False)
                except Exception as e:
                    print(f"Web server error: {e}")
            
            self.web_server_thread = threading.Thread(target=run_server, daemon=True)
            self.web_server_thread.start()
            print(f"Web interface started: http://127.0.0.1:{self.web_port}")
        except Exception as e:
            print(f"Web server startup error: {e}")
    
    def get_web_interface_html(self):
        """Web arayüzü HTML'ini döndür"""
        return '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>P2P File Sharing</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        .upload-area {
            border: 2px dashed #ccc;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            margin-bottom: 30px;
            transition: border-color 0.3s;
        }
        .upload-area:hover {
            border-color: #007bff;
        }
        .upload-area.dragover {
            border-color: #007bff;
            background-color: #f0f8ff;
        }
        .file-input {
            display: none;
        }
        .upload-btn {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        .upload-btn:hover {
            background-color: #0056b3;
        }
        .tables-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 30px;
        }
        .table-section {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
        }
        .table-section h2 {
            margin-top: 0;
            color: #495057;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        th {
            background-color: #e9ecef;
            font-weight: bold;
        }
        .btn {
            padding: 5px 10px;
            margin: 2px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }
        .btn-download {
            background-color: #28a745;
            color: white;
        }
        .btn-remove {
            background-color: #dc3545;
            color: white;
        }
        .btn:hover {
            opacity: 0.8;
        }
        .status {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }
        .status-pending {
            background-color: #fff3cd;
            color: #856404;
        }
        .status-completed {
            background-color: #d4edda;
            color: #155724;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>P2P File Sharing</h1>
        
        <div class="upload-area" id="uploadArea">
            <p>Drag and drop files here or select them</p>
            <input type="file" id="fileInput" class="file-input" multiple>
            <button class="upload-btn" onclick="document.getElementById('fileInput').click()">Select File</button>
        </div>
        
        <div class="tables-container">
            <div class="table-section">
                <h2>Pending Files</h2>
                <table id="pendingTable">
                    <thead>
                        <tr>
                            <th>File Name</th>
                            <th>Size</th>
                            <th>Upload Time</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody id="pendingTableBody">
                    </tbody>
                </table>
            </div>
            
            <div class="table-section">
                <h2>Transfer History</h2>
                <table id="historyTable">
                    <thead>
                        <tr>
                            <th>File Name</th>
                            <th>Device</th>
                            <th>Transfer Time</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="historyTableBody">
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        // Dosya yükleme işlemleri
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const files = e.dataTransfer.files;
            uploadFiles(files);
        });
        
        fileInput.addEventListener('change', (e) => {
            uploadFiles(e.target.files);
        });
        
        function uploadFiles(files) {
            for (let file of files) {
                const formData = new FormData();
                formData.append('file', file);
                
                fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        loadPendingFiles();
                    } else {
                        alert('File upload error: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Hata:', error);
                    alert('File upload error');
                });
            }
        }
        
        function loadPendingFiles() {
            fetch('/api/pending_files')
                .then(response => response.json())
                .then(files => {
                    const tbody = document.getElementById('pendingTableBody');
                    tbody.innerHTML = '';
                    
                    files.forEach(file => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${file.name}</td>
                            <td>${formatFileSize(file.size)}</td>
                            <td>${file.upload_time}</td>
                            <td>
                                <button class="btn btn-download" onclick="downloadFile('${file.id}')">İndir</button>
                                <button class="btn btn-remove" onclick="removeFile('${file.id}')">Kaldır</button>
                            </td>
                        `;
                        tbody.appendChild(row);
                    });
                });
        }
        
        function loadTransferHistory() {
            fetch('/api/transfer_history')
                .then(response => response.json())
                .then(history => {
                    const tbody = document.getElementById('historyTableBody');
                    tbody.innerHTML = '';
                    
                    history.forEach(transfer => {
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${transfer.file_name}</td>
                            <td>${transfer.device}</td>
                            <td>${transfer.transfer_time}</td>
                            <td><span class="status status-${transfer.status}">${transfer.status}</span></td>
                        `;
                        tbody.appendChild(row);
                    });
                });
        }
        
        function downloadFile(fileId) {
            window.open(`/api/download/${fileId}`, '_blank');
            setTimeout(() => {
                loadPendingFiles();
                loadTransferHistory();
            }, 1000);
        }
        
        function removeFile(fileId) {
            if (confirm('Are you sure you want to remove this file?')) {
                fetch(`/api/remove/${fileId}`, {
                    method: 'DELETE'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        loadPendingFiles();
                    } else {
                        alert('File removal error: ' + data.error);
                    }
                });
            }
        }
        
        function formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        // Sayfa yüklendiğinde verileri getir
        loadPendingFiles();
        loadTransferHistory();
        
        // Her 5 saniyede bir verileri güncelle
        setInterval(() => {
            loadPendingFiles();
            loadTransferHistory();
        }, 5000);
    </script>
</body>
</html>
        '''
    
    def start_services(self):
        """Arka plan servislerini başlat"""
        # Only web server is used, P2P features removed
        pass
    
    def open_window(self, _ = None):
        """Web arayüzünü tarayıcıda aç"""
        import webbrowser
        local_ip = self.get_local_ip()
        webbrowser.open(f"http://{local_ip}:4848")
    
    def refresh_devices(self, _ = None):
        """Cihazları yenile"""
        self.discover_devices()
        if rumps:
            rumps.notification(
                title="P2P File Transfer",
                subtitle="Devices refreshed",
                message="Ağdaki cihazlar taranıyor..."
            )
        else:
            print("Devices refreshed - Scanning network devices...")
    
    def quit_app(self, _ = None):
        """Uygulamayı kapat"""
        self.running = False
        if self.root:
            self.root.quit()
        if rumps:
            rumps.quit_application()
        else:
            sys.exit(0)
    
    def start_discovery_service(self):
        """Ağ keşif servisini başlat - Devre dışı"""
        # P2P feature removed, only web interface used
        pass
    
    def start_file_server(self):
        """Dosya sunucu servisini başlat - Devre dışı"""
        # P2P feature removed, only web interface used
        pass
    
    def handle_file_transfer(self, client_socket):
        """Gelen dosya transferini işle"""
        try:
            # Get file information
            header = client_socket.recv(1024).decode()
            file_info = json.loads(header)
            
            filename = file_info['filename']
            filesize = file_info['filesize']
            
            # Send notification to user
            if rumps:
                rumps.notification(
                    title="File Received",
            subtitle=f"Incoming file: {filename}",
                    message=f"Boyut: {filesize} bytes\nKabul etmek için uygulamayı açın."
                )
            else:
                print(f"Incoming file: {filename} (Size: {filesize} bytes)")
            
            # Simple approval mechanism - should be more advanced in real app
            result = True  # Auto accept (can be improved)
            
            if result:
                # Save file
                downloads_path = Path.home() / "Downloads"
                file_path = downloads_path / filename
                
                with open(file_path, 'wb') as f:
                    received = 0
                    while received < filesize:
                        chunk = client_socket.recv(min(8192, filesize - received))
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                
                if rumps:
                    rumps.notification(
                        title="File Received",
            subtitle="Transfer completed",
                        message=f"Dosya kaydedildi: {file_path}"
                    )
                else:
                    print(f"File received: {file_path}")
            else:
                client_socket.send(b"REJECTED")
        except Exception as e:
            print(f"File transfer error: {e}")
        finally:
            client_socket.close()
    
    def send_file(self, file_path, target_device):
        """Dosya gönder"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                if self.root:
                    messagebox.showerror("Error", "File not found!")
                return
            
            # Connect to target device
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((target_device['ip'], target_device['port']))
            
            # Send file information
            file_info = {
                'filename': file_path.name,
                'filesize': file_path.stat().st_size
            }
            client_socket.send(json.dumps(file_info).encode())
            
            # Send file
            with open(file_path, 'rb') as f:
                sent = 0
                total_size = file_path.stat().st_size
                
                while sent < total_size:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    client_socket.send(chunk)
                    sent += len(chunk)
                    
                    # Update progress
                    if self.progress_var:
                        progress = (sent / total_size) * 100
                        self.progress_var.set(progress)
                        if self.root:
                            self.root.update_idletasks()
            
            if rumps:
                rumps.notification(
                    title="File Sent",
            subtitle="Transfer completed",
                    message=f"Dosya başarıyla gönderildi: {file_path.name}"
                )
            else:
                print(f"File sent: {file_path.name}")
            
            if self.root:
                messagebox.showinfo("Success", "File sent successfully!")
            
        except Exception as e:
            error_msg = f"Dosya gönderme hatası: {e}"
            if self.root:
                messagebox.showerror("Hata", error_msg)
            else:
                if rumps:
                    rumps.notification(
                        title="Hata",
                        subtitle="File could not be sent",
                        message=str(e)
                    )
                else:
                    print(f"Error: File could not be sent - {e}")
        finally:
            if 'client_socket' in locals():
                client_socket.close()
            if self.progress_var:
                self.progress_var.set(0)
    
    def discover_devices(self):
        """Ağdaki cihazları keşfet - Devre dışı"""
        # P2P özelliği kaldırıldı, sadece web arayüzü kullanılıyor
        pass
    
    def get_local_ip(self):
        """Yerel IP adresini al"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def get_local_ip(self):
        """Yerel IP adresini al"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def open_in_finder(self):
        """Downloads klasörünü Finder'da aç"""
        downloads_path = Path.home() / "Downloads"
        subprocess.run(["open", str(downloads_path)])
    
    def on_file_drop(self, event):
        """Dosya sürükle-bırak işlemi"""
        files = self.root.tk.splitlist(event.data)
        if files and self.get_selected_device():
            self.send_file(files[0], self.get_selected_device())
        elif not self.get_selected_device():
            messagebox.showwarning("Warning", "Please select a device first!")
    
    def select_and_send_file(self):
        """Dosya seç ve gönder"""
        device = self.get_selected_device()
        if not device:
            messagebox.showwarning("Uyarı", "Lütfen önce bir cihaz seçin!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Select file to send",
            filetypes=[("Tüm dosyalar", "*.*")]
        )
        
        if file_path:
            self.send_file(file_path, device)
    
    def get_selected_device(self):
        """Seçili cihazı al"""
        if not self.device_listbox:
            return None
            
        selection = self.device_listbox.curselection()
        if selection:
            device_text = self.device_listbox.get(selection[0])
            device_id = device_text.split(" - ")[1]
            return self.devices.get(device_id)
        return None
    
    def update_device_list(self):
        """Cihaz listesini güncelle"""
        if self.device_listbox:
            self.device_listbox.delete(0, tk.END)
            for device_id, device_info in self.devices.items():
                self.device_listbox.insert(
                    tk.END,
                    f"{device_info['name']} - {device_id}"
                )
    
    def show_window(self):
        """Pencereyi göster"""
        if self.root:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', True)
            self.root.attributes('-topmost', False)
            self.discover_devices()
    
    def hide_window(self):
        """Pencereyi gizle"""
        if self.root:
            self.root.withdraw()

def main():
    """Ana fonksiyon"""
    # Check required permissions for macOS
    try:
        print("Starting P2P File Transfer...")
        app = P2PFileTransferMac()
        print("Application object created.")
        
        if rumps and app.app:
            # If rumps is available, run as menu bar application
            print("Starting rumps menu bar application...")
            app.app.run()
        else:
            # If rumps is not available, background services are running
            print("Application running in background. Use Ctrl+C to quit.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down application...")
                app.running = False
    except KeyboardInterrupt:
        print("\nUygulama kapatılıyor...")
    except Exception as e:
        import traceback
        print(f"Application error: {e}")
        print(f"Error details: {traceback.format_exc()}")

if __name__ == "__main__":
    main()