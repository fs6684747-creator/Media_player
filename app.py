import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from moviepy import VideoFileClip
from PIL import Image
import base64
from io import BytesIO


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_BeNxLMOs3VY8@ep-autumn-hat-a1gt3ej3-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024 


db = SQLAlchemy(app)
migrate = Migrate(app, db)

# User Model
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    is_channel = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'



class Video(db.Model):
    __tablename__ = "video"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(255), nullable=False)
    thumbnail = db.Column(db.Text, nullable=True)  # base64 encoded thumbnail


    def __repr__(self):
        return f"<Video {self.id} - {self.name}>"

    def to_dict(self):
        """Convert model to dictionary (for API responses)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
        }


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('upload_page'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']
        print(user_type)
        is_channel = True

        if user_type == "Channel":
            is_channel = True
        else:
            is_channel = False

        
        # Check if user already exists
        if Users.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        
        if Users.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        # Create new user
        user = Users(username=username, email=email, is_channel=is_channel)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = Users.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username

            if user.is_channel:
                return redirect(url_for('upload_page'))
            
            return redirect(url_for('videos'))
        else:
            flash('Invalid email or password')
    
    return render_template('login.html')

# Page route for video upload
@app.route("/upload", methods=["GET"])
def upload_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("upload.html")

@app.route('/videos')
def videos():
    all_videos = Video.query.all()
    return render_template('videos.html', videos=all_videos)

@app.route('/video/<int:video_id>')
def video_player(video_id):
    video = Video.query.get_or_404(video_id)
    return render_template('video_player.html', video=video)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.clear()
    return redirect(url_for('login'))


# API: Upload video
@app.route("/api/upload", methods=["POST"])
def upload_video():
    if "video" not in request.files:
        return jsonify({"error": "No video file uploaded"}), 400

    file = request.files["video"]
    thumbnail_file = request.files.get("thumbnail")  # <-- custom thumbnail (optional)
    name = request.form.get("name")
    description = request.form.get("description")

    if file.filename == "":
        return jsonify({"error": "No selected video file"}), 400

    # Step 1: Create DB record to get video ID
    new_video = Video(name=name, description=description, url="")
    db.session.add(new_video)
    db.session.flush()

    # Step 2: Save video file
    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"video_{new_video.id}{ext}"
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
    file.save(filepath)

    # Step 3: Set video URL
    new_video.url = f"/{filepath}"

    # Step 4: Handle thumbnail
    if thumbnail_file and thumbnail_file.filename != "":
        # ✅ Use uploaded image as thumbnail
        try:
            image = Image.open(thumbnail_file.stream)
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            thumbnail_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            new_video.thumbnail = thumbnail_b64
        except Exception as e:
            print(f"Failed to process uploaded thumbnail: {e}")
            new_video.thumbnail = None
    else:
        # 🔁 Fallback: generate thumbnail from video
        try:
            clip = VideoFileClip(filepath)
            frame = clip.get_frame(1)
            image = Image.fromarray(frame)

            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            thumbnail_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            new_video.thumbnail = thumbnail_b64
        except Exception as e:
            print(f"Thumbnail generation failed: {e}")
            new_video.thumbnail = None

    # Step 5: Save to DB
    db.session.commit()

    return jsonify({"message": "Video uploaded successfully", "video": new_video.to_dict()})


# API: Get all videos
@app.route("/api/videos", methods=["GET"])
def get_videos():
    videos = Video.query.all()
    return jsonify([v.to_dict() for v in videos])

if __name__ == '__main__':
    app.run(debug=True)