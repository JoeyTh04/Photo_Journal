import os
import base64
from datetime import datetime
from flask import Flask, request, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Database configuration
database_url = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/photojournal')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = int(os.environ.get('MAX_FILE_SIZE', 10))  # MB
JOURNAL_TITLE = os.environ.get('JOURNAL_TITLE', 'My Photo Journal')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE * 1024 * 1024

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# Database Models
class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), unique=True, nullable=False)  # YYYY-MM-DD format
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with photos
    photos = db.relationship('Photo', backref='entry', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'notes': self.notes,
            'photos': [photo.to_dict() for photo in self.photos],
            'created_at': self.created_at.isoformat() if self.created_at else None
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

# Create tables
with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_or_create_entry(date):
    """Get existing entry or create new one for the date"""
    entry = JournalEntry.query.filter_by(date=date).first()
    if not entry:
        entry = JournalEntry(date=date, notes='')
        db.session.add(entry)
        db.session.commit()
    return entry

@app.route('/')
def calendar():
    """Calendar view showing all dates with entries"""
    entries = JournalEntry.query.all()
    # Convert to dictionary format for template compatibility
    entries_dict = {}
    for entry in entries:
        entries_dict[entry.date] = {
            'photos': [{'url': photo.url} for photo in entry.photos],
            'notes': entry.notes,
            'date': entry.date
        }
    
    return render_template('calendar.html', 
                         entries=entries_dict, 
                         title=JOURNAL_TITLE,
                         now=datetime.now())

@app.route('/day/<date>')
def view_day(date):
    """View/edit a specific day's journal entry"""
    entry = get_or_create_entry(date)
    
    # Format for template compatibility
    entry_dict = {
        'photos': [{'url': photo.url, 'filename': photo.filename, 'id': photo.id} for photo in entry.photos],
        'notes': entry.notes,
        'date': date
    }
    
    return render_template('day.html', 
                         date=date, 
                         entry=entry_dict,
                         title=JOURNAL_TITLE)

@app.route('/save_entry/<date>', methods=['POST'])
def save_entry(date):
    """Save notes for a specific day"""
    entry = get_or_create_entry(date)
    entry.notes = request.form.get('notes', '')
    entry.updated_at = datetime.utcnow()
    db.session.commit()
    
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
        
        # Get or create entry and add photo
        entry = get_or_create_entry(date)
        
        photo = Photo(
            filename=unique_filename,
            url=f'/static/uploads/{unique_filename}',
            entry_date=date
        )
        db.session.add(photo)
        db.session.commit()
        
        return jsonify({'success': True, 'photo_url': f'/static/uploads/{unique_filename}'})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/delete_photo/<date>/<int:photo_id>', methods=['DELETE'])
def delete_photo(date, photo_id):
    """Delete a photo from a day's entry"""
    photo = Photo.query.filter_by(id=photo_id, entry_date=date).first()
    
    if photo:
        # Remove the photo file
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
        if os.path.exists(photo_path):
            os.remove(photo_path)
        
        # Remove from database
        db.session.delete(photo)
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'error': 'Photo not found'}), 404

@app.route('/api/entries')
def get_entries():
    """API endpoint to get all entries (for calendar highlighting)"""
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
    """Health check endpoint to verify database connection"""
    try:
        # Test database connection
        db.session.execute('SELECT 1')
        entry_count = JournalEntry.query.count()
        photo_count = Photo.query.count()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'app': 'Photo Journal',
            'entries': entry_count,
            'photos': photo_count,
            'database_type': 'PostgreSQL'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'database': 'disconnected',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)