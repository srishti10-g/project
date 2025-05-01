import os
import time
import requests

# Client config
LOCAL_FOLDER = 'local_folder'
SERVER_UPLOAD_URL = 'http://127.0.0.1:5000/upload'
SERVER_DELETE_URL = 'http://127.0.0.1:5000/delete'
SYNC_INTERVAL = 10  # seconds

# In-memory dictionary to track last known modification times of synced files
file_mod_times = {}

def get_all_files(base_folder):
    """
    Return list of relative file and directory paths under base_folder.
    Include files only for upload; directories handled for deletion if empty.
    """
    file_list = []
    for root, dirs, files in os.walk(base_folder):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, base_folder)
            file_list.append(rel_path)
    return file_list

def upload_file(rel_path):
    """
    Upload a file to the server.
    """
    full_path = os.path.join(LOCAL_FOLDER, rel_path)
    with open(full_path, 'rb') as f:
        files = {'file': f}
        data = {'filepath': rel_path}
        try:
            resp = requests.post(SERVER_UPLOAD_URL, files=files, data=data)
            if resp.status_code == 200:
                print(f'Uploaded: {rel_path}')
                return True
            else:
                print(f'Failed to upload {rel_path}: {resp.text}')
                return False
        except Exception as e:
            print(f'Exception uploading {rel_path}: {e}')
            return False

def delete_path(rel_path):
    """
    Request server to delete file or empty directory at rel_path.
    """
    try:
        resp = requests.post(SERVER_DELETE_URL, json={'filepath': rel_path})
        if resp.status_code == 200:
            print(f'Deleted on server: {rel_path}')
            return True
        else:
            print(f'Failed to delete {rel_path} on server: {resp.text}')
            return False
    except Exception as e:
        print(f'Exception deleting {rel_path} on server: {e}')
        return False

def sync():
    """
    Perform sync:
    - detect new and modified files and upload them
    - detect deleted files and request deletion on server
    """
    global file_mod_times
    current_files = set(get_all_files(LOCAL_FOLDER))
    previous_files = set(file_mod_times.keys())

    # Files deleted locally
    deleted_files = previous_files - current_files
    # Files new or modified
    new_or_modified_files = []

    for rel_path in current_files:
        full_path = os.path.join(LOCAL_FOLDER, rel_path)
        mod_time = os.path.getmtime(full_path)
        if (rel_path not in file_mod_times) or (file_mod_times[rel_path] < mod_time):
            new_or_modified_files.append(rel_path)

    # Upload new or modified files
    for rel_path in new_or_modified_files:
        if upload_file(rel_path):
            file_mod_times[rel_path] = os.path.getmtime(os.path.join(LOCAL_FOLDER, rel_path))

    # Request delete for files deleted locally
    for rel_path in deleted_files:
        if delete_path(rel_path):
            file_mod_times.pop(rel_path)

    # Optional: also handle empty directories deleted locally
    # Note: For simplicity, only deleting empty directories on server on explicit delete requests
    # Could implement directory scanning and deletions if needed

def main():
    print("Starting repository directory synchronization client.")
    print(f"Local folder to sync: {LOCAL_FOLDER}")
    print(f"Server upload URL: {SERVER_UPLOAD_URL}")
    print(f"Server delete URL: {SERVER_DELETE_URL}")

    if not os.path.exists(LOCAL_FOLDER):
        print(f"Local folder '{LOCAL_FOLDER}' does not exist. Creating it.")
        os.makedirs(LOCAL_FOLDER)

    while True:
        sync()
        time.sleep(SYNC_INTERVAL)

if __name__ == '__main__':
    main()
