import os
import sys
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Database configuration with better error handling
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Convert to psycopg3 driver format
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# File upload configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10))
JOURNAL_TITLE = os.environ.get('JOURNAL_TITLE', 'My Photo Journal')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * 1024 * 1024

# Create upload folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# Database Models
class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    photos = db.relationship('Photo', backref='entry', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'notes': self.notes,
            'photos': [p.to_dict() for p in self.photos],
        }

class Photo(db.Model):
    __tablename__ = 'photos'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    entry_date = db.Column(db.String(20), db.ForeignKey('journal_entries.date'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'url': self.url,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }

# Create tables with error handling
try:
    with app.app_context():
        db.create_all()
        print("Database tables created successfully")
except Exception as e:
    print(f"Database initialization error: {e}")
    sys.exit(1)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_entry(date):
    entry = JournalEntry.query.filter_by(date=date).first()
    if not entry:
        entry = JournalEntry(date=date, notes='')
        db.session.add(entry)
        db.session.commit()
    return entry

@app.route('/')
def calendar():
    entries = JournalEntry.query.all()
    entries_dict = {}
    for entry in entries:
        entries_dict[entry.date] = {
            'photos': [{'url': p.url} for p in entry.photos],
            'notes': entry.notes,
            'date': entry.date
        }
    return render_template('calendar.html', 
                         entries=entries_dict, 
                         title=JOURNAL_TITLE,
                         now=datetime.now())

@app.route('/day/<date>')
def view_day(date):
    entry = get_or_create_entry(date)
    entry_dict = {
        'photos': [{'url': p.url, 'filename': p.filename, 'id': p.id} for p in entry.photos],
        'notes': entry.notes,
        'date': date
    }
    return render_template('day.html', 
                         date=date, 
                         entry=entry_dict,
                         title=JOURNAL_TITLE)

@app.route('/save_entry/<date>', methods=['POST'])
def save_entry(date):
    entry = get_or_create_entry(date)
    entry.notes = request.form.get('notes', '')
    entry.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Notes saved!'})

@app.route('/upload_photo/<date>', methods=['POST'])
def upload_photo(date):
    if 'photo' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['photo']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)
        
        entry = get_or_create_entry(date)
        photo = Photo(
            filename=unique_filename,
            url=f'/static/uploads/{unique_filename}',
            entry_date=date
        )
        db.session.add(photo)
        db.session.commit()
        
        return jsonify({'success': True, 'photo_url': f'/static/uploads/{unique_filename}', 'photo_id': photo.id})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/delete_photo/<date>/<int:photo_id>', methods=['DELETE'])
def delete_photo(date, photo_id):
    photo = Photo.query.filter_by(id=photo_id, entry_date=date).first()
    if photo:
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(photo_path):
            os.remove(photo_path)
        db.session.delete(photo)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'Photo not found'}), 404

@app.route('/api/entries')
def get_entries():
    entries = JournalEntry.query.all()
    entries_dict = {}
    for entry in entries:
        entries_dict[entry.date] = {
            'photos': [{'url': p.url} for p in entry.photos],
            'notes': entry.notes
        }
    return jsonify(entries_dict)

@app.route('/health')
def health():
    try:
        db.session.execute('SELECT 1')
        entry_count = JournalEntry.query.count()
        photo_count = Photo.query.count()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'app': 'Photo Journal',
            'entries': entry_count,
            'photos': photo_count,
            'python_version': sys.version
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)