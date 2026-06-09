import os
import uuid
import time
from flask import current_app

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif'})

def save_profile_picture(file, nim):
    if not file or file.filename == '':
        return None
    
    if not allowed_file(file.filename):
        raise ValueError("Tipe file tidak diizinkan. Gunakan PNG, JPG, JPEG, atau GIF.")
    
    # Buat nama unik: nim_timestamp_uuid.ext
    ext = file.filename.rsplit('.', 1)[1].lower()
    timestamp = int(time.time())
    filename = f"{nim}_{timestamp}_{uuid.uuid4().hex}.{ext}"
    
    # 🔥 GUNAKAN FOLDER storage/uploads
    upload_dir = current_app.config.get('UPLOAD_FOLDER')
    if not upload_dir:
        upload_dir = os.path.join(current_app.root_path, 'storage', 'uploads')
    
    # Buat folder jika belum ada
    os.makedirs(upload_dir, exist_ok=True)
    
    # Simpan file
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    print(f"✅ File saved to: {filepath}")
    
    # 🔥 KEMBALIKAN PATH RELATIVE
    root_dir = os.path.dirname(current_app.root_path)
    relative_path = os.path.relpath(filepath, root_dir)
    relative_path = relative_path.replace('\\', '/')
    
    print(f"📁 Relative path: {relative_path}")
    
    return relative_path