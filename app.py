import os
import json
from datetime import datetime
from flask import Flask, request, render_template, jsonify, redirect, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10))  # MB
JOURNAL_TITLE = os.environ.get('JOURNAL_TITLE', 'My Photo Journal')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * 1024 * 1024

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

JOURNAL_FILE = 'journal_entries.json'

def load_entries():
    """Load journal entries from JSON file"""
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_entries(entries):
    """Save journal entries to JSON file"""
    with open(JOURNAL_FILE, 'w') as f:
        json.dump(entries, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def calendar():
    """Calendar view showing all dates with entries"""
    entries = load_entries()
    return render_template('calendar.html', 
                         entries=entries, 
                         title=JOURNAL_TITLE,
                         now=datetime.now())

@app.route('/day/<date>')
def view_day(date):
    """View/edit a specific day's journal entry"""
    entries = load_entries()
    entry = entries.get(date, {'photos': [], 'notes': '', 'date': date})
    return render_template('day.html', 
                         date=date, 
                         entry=entry,
                         title=JOURNAL_TITLE)

@app.route('/save_entry/<date>', methods=['POST'])
def save_entry(date):
    """Save notes for a specific day"""
    entries = load_entries()
    
    if date not in entries:
        entries[date] = {'photos': [], 'notes': '', 'date': date}
    
    entries[date]['notes'] = request.form.get('notes', '')
    save_entries(entries)
    
    return jsonify({'success': True, 'message': 'Notes saved!'})

@app.route('/upload_photo/<date>', methods=['POST'])
def upload_photo(date):
    """Upload a photo for a specific day"""
    if 'photo' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['photo']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Add timestamp to avoid duplicates
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        # Save to journal entries
        entries = load_entries()
        if date not in entries:
            entries[date] = {'photos': [], 'notes': '', 'date': date}
        
        entries[date]['photos'].append({
            'filename': unique_filename,
            'url': f'/static/uploads/{unique_filename}',
            'uploaded_at': datetime.now().isoformat()
        })
        save_entries(entries)
        
        return jsonify({'success': True, 'photo_url': f'/static/uploads/{unique_filename}'})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/delete_photo/<date>/<int:photo_index>', methods=['DELETE'])
def delete_photo(date, photo_index):
    """Delete a photo from a day's entry"""
    entries = load_entries()
    
    if date in entries and photo_index < len(entries[date]['photos']):
        # Remove the photo file
        photo = entries[date]['photos'][photo_index]
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo['filename'])
        if os.path.exists(photo_path):
            os.remove(photo_path)
        
        # Remove from entries
        entries[date]['photos'].pop(photo_index)
        save_entries(entries)
        return jsonify({'success': True})
    
    return jsonify({'error': 'Photo not found'}), 404

@app.route('/api/entries')
def get_entries():
    """API endpoint to get all entries (for calendar highlighting)"""
    entries = load_entries()
    return jsonify(entries)

@app.route('/health')
def health():
    return {'status': 'ok', 'app': 'Photo Journal', 'entries': len(load_entries())}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True)