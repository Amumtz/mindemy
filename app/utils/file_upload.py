import os
import uuid
import time                     # ← tambahkan import time
from flask import current_app
from werkzeug.utils import secure_filename

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def save_profile_picture(file, nim):
    if not file or file.filename == '':
        return None
    
    if not allowed_file(file.filename):
        raise ValueError("Tipe file tidak diizinkan. Gunakan PNG, JPG, JPEG, atau GIF.")
    
    # Buat nama unik: nim_timestamp_uuid.ext
    ext = file.filename.rsplit('.', 1)[1].lower()
    # ✅ Perbaikan: gunakan time.time() bukan os.path.timestamp
    filename = f"{nim}_{int(time.time())}_{uuid.uuid4().hex}.{ext}"
    
    upload_dir = current_app.config['PROFILE_PHOTO_FOLDER']  
    os.makedirs(upload_dir, exist_ok=True)
    
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    # Kembalikan path relatif yang disimpan di DB
    return os.path.join(upload_dir, filename).replace('\\', '/')