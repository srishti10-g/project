# server_app.py
import os
import socket
import hashlib
import threading
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTextEdit, 
                            QVBoxLayout, QWidget, QPushButton)
from PyQt5.QtCore import QThread, pyqtSignal

class ServerThread(QThread):
    log_signal = pyqtSignal(str)
    client_signal = pyqtSignal(str)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.running = False
        self.clients = {}
        self.sync_folder = 'server_sync_folder'
        
        if not os.path.exists(self.sync_folder):
            os.makedirs(self.sync_folder)

    def run(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        self.log_signal.emit(f"[*] Server started on {self.host}:{self.port}")
        
        try:
            while self.running:
                client_socket, address = self.server_socket.accept()
                self.client_signal.emit(f"[+] {address} connected")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.start()
        except Exception as e:
            self.log_signal.emit(f"[!] Server error: {e}")
        finally:
            self.server_socket.close()

    def stop(self):
        self.running = False
        # Create a dummy connection to unblock the accept call
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((self.host, self.port))
        except:
            pass

    def handle_client(self, client_socket, address):
        try:
            while True:
                command = client_socket.recv(4096).decode()
                if not command:
                    break
                
                self.client_signal.emit(f"[{address}] Command: {command[:50]}")
                
                if command.startswith("SYNC_REQUEST"):
                    self.handle_sync_request(client_socket)
                elif command.startswith("UPLOAD"):
                    filename = command.split()[1]
                    self.receive_file(client_socket, filename)
                elif command.startswith("DOWNLOAD"):
                    filename = command.split()[1]
                    self.send_file(client_socket, filename)
                elif command.startswith("DELETE"):
                    filename = command.split()[1]
                    self.delete_file(filename)
                    client_socket.send(b"DELETE_ACK")
        except Exception as e:
            self.client_signal.emit(f"[!] Client {address} error: {e}")
        finally:
            client_socket.close()
            self.client_signal.emit(f"[-] {address} disconnected")

    def handle_sync_request(self, client_socket):
        """Send the list of files with their hashes to the client"""
        file_list = {}
        for root, dirs, files in os.walk(self.sync_folder):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, self.sync_folder)
                file_list[relative_path] = self.get_file_hash(file_path)
        
        # Send file list to client
        client_socket.send(json.dumps(file_list).encode())

    def receive_file(self, client_socket, filename):
        """Receive a file from the client and save it"""
        file_path = os.path.join(self.sync_folder, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Receive file size first
        file_size = int(client_socket.recv(4096).decode())
        client_socket.send(b"READY")
        
        # Receive file data
        with open(file_path, 'wb') as f:
            bytes_received = 0
            while bytes_received < file_size:
                data = client_socket.recv(4096)
                if not data:
                    break
                f.write(data)
                bytes_received += len(data)
        
        self.client_signal.emit(f"[*] Received file: {filename}")
        client_socket.send(b"UPLOAD_ACK")

    def send_file(self, client_socket, filename):
        """Send a file to the client"""
        file_path = os.path.join(self.sync_folder, filename)
        if not os.path.exists(file_path):
            client_socket.send(b"FILE_NOT_FOUND")
            return
        
        # Send file size first
        file_size = os.path.getsize(file_path)
        client_socket.send(str(file_size).encode())
        
        # Wait for client to be ready
        response = client_socket.recv(4096)
        if response != b"READY":
            return
        
        # Send file data
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                client_socket.send(data)
        
        self.client_signal.emit(f"[*] Sent file: {filename}")

    def delete_file(self, filename):
        """Delete a file from the server"""
        file_path = os.path.join(self.sync_folder, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            self.client_signal.emit(f"[*] Deleted file: {filename}")

    def get_file_hash(self, file_path):
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Sync Server")
        self.setGeometry(100, 100, 800, 600)
        
        self.server_thread = None
        
        # UI Elements
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        
        self.start_btn = QPushButton("Start Server")
        self.start_btn.clicked.connect(self.toggle_server)
        
        self.client_list = QTextEdit()
        self.client_list.setReadOnly(True)
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.start_btn)
        layout.addWidget(self.log_area)
        layout.addWidget(self.client_list)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
    def toggle_server(self):
        if self.server_thread and self.server_thread.isRunning():
            self.stop_server()
        else:
            self.start_server()
    
    def start_server(self):
        self.server_thread = ServerThread('0.0.0.0', 5000)
        self.server_thread.log_signal.connect(self.log_message)
        self.server_thread.client_signal.connect(self.client_message)
        self.server_thread.start()
        self.start_btn.setText("Stop Server")
    
    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread.wait()
            self.log_message("[*] Server stopped")
            self.start_btn.setText("Start Server")
    
    def log_message(self, message):
        self.log_area.append(message)
    
    def client_message(self, message):
        self.client_list.append(message)
    
    def closeEvent(self, event):
        self.stop_server()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication([])
    window = ServerWindow()
    window.show()
    app.exec_()