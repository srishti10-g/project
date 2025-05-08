# client_app.py
import os
import socket
import hashlib
import json
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, 
                            QVBoxLayout, QWidget, QPushButton, 
                            QLabel, QLineEdit, QHBoxLayout)
from PyQt5.QtCore import QThread, pyqtSignal

class SyncThread(QThread):
    log_signal = pyqtSignal(str)
    sync_signal = pyqtSignal(str)

    def __init__(self, server_host, server_port, sync_folder):
        super().__init__()
        self.server_host = server_host
        self.server_port = server_port
        self.sync_folder = sync_folder
        self.running = False
        self.syncing = False
        self.client_socket = None
        
        if not os.path.exists(self.sync_folder):
            os.makedirs(self.sync_folder)

    def run(self):
        self.running = True
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((self.server_host, self.server_port))
            self.log_signal.emit("[*] Connected to server")
            
            # Start filesystem observer
            event_handler = SyncEventHandler(self)
            self.observer = Observer()
            self.observer.schedule(event_handler, self.sync_folder, recursive=True)
            self.observer.start()
            
            while self.running:
                time.sleep(10)  # Sync interval
                if self.running:
                    self.full_sync()
        except Exception as e:
            self.log_signal.emit(f"[!] Connection error: {e}")
        finally:
            if hasattr(self, 'observer'):
                self.observer.stop()
                self.observer.join()
            if self.client_socket:
                self.client_socket.close()
            self.log_signal.emit("[-] Disconnected from server")

    def stop(self):
        self.running = False

    def full_sync(self):
        if self.syncing:
            return
        
        self.syncing = True
        try:
            self.log_signal.emit("[*] Starting sync...")
            
            # Get server file list
            self.client_socket.send(b"SYNC_REQUEST")
            server_files = json.loads(self.client_socket.recv(4096).decode())
            
            # Get local file list
            local_files = {}
            for root, dirs, files in os.walk(self.sync_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.sync_folder)
                    local_files[relative_path] = self.get_file_hash(file_path)
            
            # Compare and sync
            for file, server_hash in server_files.items():
                if file not in local_files or local_files[file] != server_hash:
                    self.download_file(file)
            
            for file, local_hash in local_files.items():
                if file not in server_files or server_files[file] != local_hash:
                    self.upload_file(file)
            
            for file in server_files:
                if file not in local_files:
                    self.client_socket.send(f"DELETE {file}".encode())
                    self.client_socket.recv(4096)  # Wait for ack
            
            self.sync_signal.emit("[*] Sync completed")
        except Exception as e:
            self.log_signal.emit(f"[!] Sync error: {e}")
        finally:
            self.syncing = False

    def upload_file(self, filename):
        file_path = os.path.join(self.sync_folder, filename)
        if not os.path.exists(file_path):
            return
        
        try:
            # Send upload command
            self.client_socket.send(f"UPLOAD {filename}".encode())
            
            # Send file size
            file_size = os.path.getsize(file_path)
            self.client_socket.send(str(file_size).encode())
            
            # Wait for server to be ready
            response = self.client_socket.recv(4096)
            if response != b"READY":
                return
            
            # Send file data
            with open(file_path, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    self.client_socket.send(data)
            
            # Wait for ack
            self.client_socket.recv(4096)
            self.log_signal.emit(f"[*] Uploaded file: {filename}")
        except Exception as e:
            self.log_signal.emit(f"[!] Upload error for {filename}: {e}")

    def download_file(self, filename):
        file_path = os.path.join(self.sync_folder, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            # Send download command
            self.client_socket.send(f"DOWNLOAD {filename}".encode())
            
            # Check if file exists on server
            response = self.client_socket.recv(4096)
            if response == b"FILE_NOT_FOUND":
                return
            
            # Receive file size
            file_size = int(response.decode())
            self.client_socket.send(b"READY")
            
            # Receive file data
            with open(file_path, 'wb') as f:
                bytes_received = 0
                while bytes_received < file_size:
                    data = self.client_socket.recv(4096)
                    if not data:
                        break
                    f.write(data)
                    bytes_received += len(data)
            
            self.log_signal.emit(f"[*] Downloaded file: {filename}")
        except Exception as e:
            self.log_signal.emit(f"[!] Download error for {filename}: {e}")

    def delete_file(self, filename):
        file_path = os.path.join(self.sync_folder, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            self.log_signal.emit(f"[*] Deleted file: {filename}")

    def get_file_hash(self, file_path):
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

class SyncEventHandler(FileSystemEventHandler):
    def __init__(self, sync_thread):
        self.sync_thread = sync_thread
    
    def on_modified(self, event):
        if not event.is_directory:
            relative_path = os.path.relpath(event.src_path, self.sync_thread.sync_folder)
            threading.Thread(target=self.sync_thread.upload_file, args=(relative_path,)).start()
    
    def on_created(self, event):
        if not event.is_directory:
            relative_path = os.path.relpath(event.src_path, self.sync_thread.sync_folder)
            threading.Thread(target=self.sync_thread.upload_file, args=(relative_path,)).start()
    
    def on_deleted(self, event):
        if not event.is_directory:
            relative_path = os.path.relpath(event.src_path, self.sync_thread.sync_folder)
            threading.Thread(target=self.sync_thread.client_socket.send, 
                           args=(f"DELETE {relative_path}".encode(),)).start()

class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Sync Client")
        self.setGeometry(100, 100, 800, 600)
        
        self.sync_thread = None
        
        # UI Elements
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        
        self.server_label = QLabel("Server:")
        self.server_input = QLineEdit("localhost")
        self.port_label = QLabel("Port:")
        self.port_input = QLineEdit("5000")
        
        self.folder_label = QLabel("Sync Folder:")
        self.folder_input = QLineEdit("client_sync_folder")
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        self.sync_btn = QPushButton("Sync Now")
        self.sync_btn.clicked.connect(self.manual_sync)
        self.sync_btn.setEnabled(False)
        
        # Layout
        server_layout = QHBoxLayout()
        server_layout.addWidget(self.server_label)
        server_layout.addWidget(self.server_input)
        server_layout.addWidget(self.port_label)
        server_layout.addWidget(self.port_input)
        
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.folder_input)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.connect_btn)
        button_layout.addWidget(self.sync_btn)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(server_layout)
        main_layout.addLayout(folder_layout)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.log_area)
        
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        
    def toggle_connection(self):
        if self.sync_thread and self.sync_thread.isRunning():
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        server_host = self.server_input.text()
        server_port = int(self.port_input.text())
        sync_folder = self.folder_input.text()
        
        self.sync_thread = SyncThread(server_host, server_port, sync_folder)
        self.sync_thread.log_signal.connect(self.log_message)
        self.sync_thread.sync_signal.connect(self.log_message)
        self.sync_thread.start()
        
        self.connect_btn.setText("Disconnect")
        self.sync_btn.setEnabled(True)
    
    def disconnect(self):
        if self.sync_thread:
            self.sync_thread.stop()
            self.sync_thread.wait()
            self.log_message("[-] Disconnected from server")
            self.connect_btn.setText("Connect")
            self.sync_btn.setEnabled(False)
    
    def manual_sync(self):
        if self.sync_thread and self.sync_thread.isRunning():
            threading.Thread(target=self.sync_thread.full_sync).start()
    
    def log_message(self, message):
        self.log_area.append(message)
    
    def closeEvent(self, event):
        self.disconnect()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication([])
    window = ClientWindow()
    window.show()
    app.exec_()