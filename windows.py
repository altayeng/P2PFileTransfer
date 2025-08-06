#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows P2P File Transfer Application
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
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
# tkinterdnd2 import - disable on error
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_AVAILABLE = True
except ImportError:
    print("tkinterdnd2 not found. Drag & drop feature disabled.")
    DND_FILES = None
    TkinterDnD = None
    DRAG_DROP_AVAILABLE = False
except Exception as e:
    print(f"tkinterdnd2 installation error: {e}. Drag & drop feature disabled.")
    DND_FILES = None
    TkinterDnD = None
    DRAG_DROP_AVAILABLE = False
import pystray
from PIL import Image, ImageDraw
import requests
from io import BytesIO
from flask import Flask, render_template_string, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
import uuid

class P2PFileTransfer:
    def __init__(self):
        self.web_port = 4848
        self.device_name = socket.gethostname()
        self.devices = {}
        self.server_socket = None
        self.discovery_socket = None
        self.running = True
        self.tray_icon = None
        
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
        
    def create_icon(self):
        """Tray simgesi oluştur"""
        # Create a simple icon
        image = Image.new('RGB', (64, 64), color='blue')
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill='white')
        draw.text((20, 25), 'FT', fill='blue')
        return image
    
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
 
    def start_discovery_service(self):
        """Ağ keşif servisini başlat"""
        def discovery_thread():
            try:
                self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Discovery port removed
                
                while self.running:
                    try:
                        data, addr = self.discovery_socket.recvfrom(1024)
                        message = json.loads(data.decode())
                        
                        if message['type'] == 'discovery':
                            # Respond to discovery request
                            response = {
                                'type': 'response',
                                'device_name': self.device_name,
                                'ip': self.get_local_ip(),
                                # Port removed
                            }
                            self.discovery_socket.sendto(
                                json.dumps(response).encode(), addr
                            )
                        elif message['type'] == 'response':
                            # New device discovered
                            device_id = f"{message['ip']}:{message['port']}"
                            self.devices[device_id] = {
                                'name': message['device_name'],
                                'ip': message['ip'],
                                'port': message['port'],
                                'last_seen': time.time()
                            }
                            self.update_device_list()
                    except Exception as e:
                        if self.running:
                            print(f"Discovery error: {e}")
            except Exception as e:
                print(f"Discovery service error: {e}")
        
        threading.Thread(target=discovery_thread, daemon=True).start()
    
    def start_file_server(self):
        """Dosya sunucu servisini başlat"""
        def server_thread():
            try:
                self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Server port removed
                self.server_socket.listen(5)
                
                while self.running:
                    try:
                        client_socket, addr = self.server_socket.accept()
                        threading.Thread(
                            target=self.handle_file_transfer,
                            args=(client_socket,),
                            daemon=True
                        ).start()
                    except Exception as e:
                        if self.running:
                            print(f"Server error: {e}")
            except Exception as e:
                print(f"File server error: {e}")
        
        threading.Thread(target=server_thread, daemon=True).start()
    
    def handle_file_transfer(self, client_socket):
        """Gelen dosya transferini işle"""
        try:
            # Get file information
            header = client_socket.recv(1024).decode()
            file_info = json.loads(header)
            
            filename = file_info['filename']
            filesize = file_info['filesize']
            
            # Get user approval
            result = messagebox.askyesno(
                "Dosya Alımı",
                f"{filename} dosyasını almak istiyor musunuz?\nBoyut: {filesize} bytes"
            )
            
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
                
                messagebox.showinfo("Success", f"File received successfully: {file_path}")
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
                        self.root.update_idletasks()
            
            messagebox.showinfo("Success", "File sent successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"File sending error: {e}")
        finally:
            if 'client_socket' in locals():
                client_socket.close()
            if self.progress_var:
                self.progress_var.set(0)
    
    def discover_devices(self):
        """Ağdaki cihazları keşfet"""
        try:
            broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            message = {
                'type': 'discovery',
                'device_name': self.device_name
            }
            
            broadcast_socket.sendto(
                json.dumps(message).encode(),
                # Discovery port removed
            )
            broadcast_socket.close()
        except Exception as e:
            print(f"Device discovery error: {e}")
    
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
    
    def create_dummy_root(self):
        """Minimal root window oluştur (tray için gerekli)"""
        try:
            self.root = tk.Tk()
            self.root.withdraw()  # Hemen gizle
            print("Minimal root window created.")
        except Exception as e:
            print(f"Root window creation error: {e}")
    
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
            messagebox.showwarning("Warning", "Please select a device first!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Select file to send",
            filetypes=[("Tüm dosyalar", "*.*")]
        )
        
        if file_path:
            self.send_file(file_path, device)
    
    def get_selected_device(self):
        """Seçili cihazı al"""
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
        self.root.deiconify()
        self.root.lift()
        self.discover_devices()
    
    def hide_window(self):
        """Pencereyi gizle"""
        self.root.withdraw()
    
    def quit_app(self):
        """Uygulamayı kapat"""
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.quit()
    
    def create_tray_menu(self):
        """Tray menüsü oluştur"""
        local_ip = self.get_local_ip()
        return pystray.Menu(
            pystray.MenuItem(f"Web Arayüzü: http://{local_ip}:4848", lambda: None),
            pystray.MenuItem(f"Yerel Erişim: http://127.0.0.1:4848", lambda: None),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Cihazları Yenile", self.discover_devices),
            pystray.MenuItem("Çıkış", self.quit_app)
        )
    
    def run(self):
        """Uygulamayı başlat"""
        try:
            print("Creating minimal root...")
            # Create minimal root (required for tray)
            self.create_dummy_root()
            print("Minimal root created.")
            
            print("Starting services...")
            # Start services
            self.start_discovery_service()
            self.start_file_server()
            print("Services started.")
            
            print("Creating tray icon...")
            # Create tray icon
            icon_image = self.create_icon()
            self.tray_icon = pystray.Icon(
                "P2P File Transfer",
                icon_image,
                "P2P File Transfer",
                self.create_tray_menu()
            )
            print("Tray icon created.")
            
            # Initial discovery
            print("Starting device discovery...")
            self.discover_devices()
            
            # Run tray icon (blocking)
            print("Starting tray icon...")
            self.tray_icon.run()
            
        except Exception as e:
            import traceback
            print(f"Run metodunda hata: {e}")
            print(f"Error details: {traceback.format_exc()}")
            raise

if __name__ == "__main__":
    try:
        print("Starting P2P File Transfer...")
        app = P2PFileTransfer()
        print("Application object created.")
        app.run()
    except Exception as e:
        import traceback
        print(f"Application error: {e}")
        print(f"Error details: {traceback.format_exc()}")
        input("Press Enter to exit...")