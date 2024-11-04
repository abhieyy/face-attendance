from flask import Flask, render_template, request, Response, make_response, flash, redirect
from flask_socketio import SocketIO, emit
import os
import cv2
import pandas as pd
import numpy as np
from datetime import datetime
from deepface import DeepFace
from sklearn.metrics.pairwise import cosine_similarity
import base64
import io
from PIL import Image
from functools import wraps
from werkzeug.utils import secure_filename
from flask import url_for
import secrets
from time import time

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'known_faces'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
socketio = SocketIO(app)

KNOWN_FACES_DIR = 'known_faces'
known_face_encodings = []
known_face_names = []

def init_app():
    if not os.path.exists('known_faces'):
        os.makedirs('known_faces')
    
    if not os.path.exists('attendance.csv'):
        reset_attendance()
    else:
        try:
            pd.read_csv('attendance.csv')
        except:
            reset_attendance()
    
    load_known_faces()

def reset_attendance():
    attendance_df = pd.DataFrame(columns=["Name", "Time"])
    attendance_df.to_csv("attendance.csv", index=False)
    print("Attendance file has been reset.")

def load_known_faces():
    known_face_encodings.clear()
    known_face_names.clear()
    for person_name in os.listdir(KNOWN_FACES_DIR):
        person_dir = os.path.join(KNOWN_FACES_DIR, person_name)
        if os.path.isdir(person_dir):
            for filename in os.listdir(person_dir):
                if allowed_file(filename):
                    image_path = os.path.join(person_dir, filename)
                    try:
                        embedding = DeepFace.represent(image_path, model_name='VGG-Face')[0]["embedding"]
                        known_face_encodings.append(embedding)
                        known_face_names.append(person_name)
                        print(f"Loaded face encoding for {person_name}")
                    except Exception as e:
                        print(f"Error processing {filename}: {str(e)}")
    print(f"Loaded {len(known_face_encodings)} face encodings")

def mark_attendance(name):
    print(f"Attempting to mark attendance for {name}")
    try:
        attendance_df = pd.read_csv("attendance.csv")
        current_time = datetime.now()
        current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Filter today's attendance for this person
        today_date = current_time.strftime('%Y-%m-%d')
        person_attendance = attendance_df[
            (attendance_df['Name'] == name) & 
            (attendance_df['Time'].str[:10] == today_date)
        ]
        
        if person_attendance.empty:
            # First attendance of the day
            new_entry = pd.DataFrame([[name, current_time_str]], columns=["Name", "Time"])
            attendance_df = pd.concat([attendance_df, new_entry], ignore_index=True)
            attendance_df.to_csv("attendance.csv", index=False)
            print(f"First attendance marked for {name} at {current_time_str}")
            socketio.emit('attendance_update', {'name': name, 'time': current_time_str})
        else:
            # Check the time difference from last attendance
            last_attendance = datetime.strptime(person_attendance['Time'].iloc[-1], '%Y-%m-%d %H:%M:%S')
            time_difference = current_time - last_attendance
            
            # Allow new entry if more than 1 hour has passed
            if time_difference.total_seconds() > 3600:  # 3600 seconds = 1 hour
                new_entry = pd.DataFrame([[name, current_time_str]], columns=["Name", "Time"])
                attendance_df = pd.concat([attendance_df, new_entry], ignore_index=True)
                attendance_df.to_csv("attendance.csv", index=False)
                print(f"New attendance marked for {name} at {current_time_str}")
                socketio.emit('attendance_update', {'name': name, 'time': current_time_str})
            else:
                minutes_to_wait = 60 - (time_difference.total_seconds() // 60)
                print(f"Please wait {int(minutes_to_wait)} minutes before marking attendance again for {name}")
                socketio.emit('attendance_message', {
                    'message': f"Please wait {int(minutes_to_wait)} minutes before marking attendance again"
                })
                
    except Exception as e:
        print(f"Error marking attendance: {str(e)}")

@socketio.on('video_frame')
def handle_video_frame(data):
    try:
        print(f"Number of known faces: {len(known_face_encodings)}")
        print(f"Known names: {known_face_names}")
        
        image_data = base64.b64decode(data.split(',')[1])
        image = Image.open(io.BytesIO(image_data))
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Replace extract_faces with detectFace
        try:
            face = DeepFace.detectFace(img, detector_backend="opencv")
            faces = [{"face": face}]  # Wrap in similar format as before
        except:
            faces = []
        
        if faces:
            print("Face detected")
            face_img = faces[0]["face"]
            embedding = DeepFace.represent(face_img, model_name="VGG-Face", enforce_detection=False)[0]["embedding"]
            
            most_similar_name = "Unknown"
            highest_similarity = 0.0

            for idx, known_encoding in enumerate(known_face_encodings):
                similarity = cosine_similarity([embedding], [known_encoding])[0][0]
                print(f"Similarity with {known_face_names[idx]}: {similarity}")
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    most_similar_name = known_face_names[idx]

            print(f"Most similar: {most_similar_name} with similarity: {highest_similarity}")
            
            if most_similar_name != "Unknown" and highest_similarity > 0.25:
                mark_attendance(most_similar_name)
        else:
            print("No face detected")
            
    except Exception as e:
        print(f"Error processing video frame: {str(e)}")

@app.route('/')
def home():
    return render_template('index.html')

def check_auth(username, password):
    return username == 'admin' and password == '123'

def authenticate():
    timestamp = str(int(time()))
    random_component = secrets.token_urlsafe(8)
    response = Response(
        'Authentication required\n', 
        401,
        {
            'WWW-Authenticate': f'Basic realm="Login-{timestamp}-{random_component}"',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )
    return response

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
            
        response = make_response(f(*args, **kwargs))
        response.headers.extend({
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'WWW-Authenticate': f'Basic realm="Login-{int(time())}-{secrets.token_urlsafe(8)}"'
        })
        return response
    
    return decorated

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
@requires_auth
def upload():
    if request.method == 'POST':
        person_name = request.form.get('person_name')
        
        if not person_name:
            flash('Please provide a person name')
            return render_template('upload.html', error="No person name provided")
        
        if 'files[]' not in request.files:
            flash('No files selected')
            return render_template('upload.html', error="No files selected")
        
        files = request.files.getlist('files[]')
        
        if not files or all(file.filename == '' for file in files):
            flash('No files selected')
            return render_template('upload.html', error="No files selected")
        
        person_dir = os.path.join(app.config['UPLOAD_FOLDER'], person_name)
        if not os.path.exists(person_dir):
            os.makedirs(person_dir)
        
        success_count = 0
        for file in files:
            if file and allowed_file(file.filename):
                try:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(person_dir, filename)
                    file.save(filepath)
                    success_count += 1
                except Exception as e:
                    flash(f'Error processing file {filename}: {str(e)}')
        
        if success_count > 0:
            flash(f'Successfully uploaded {success_count} files')
            load_known_faces()
            return redirect(url_for('upload'))
        else:
            flash('No files were successfully uploaded')
            return render_template('upload.html', error="Upload failed")
            
    return render_template('upload.html')

@app.after_request
def add_security_headers(response):
    timestamp = str(int(time()))
    random_component = secrets.token_urlsafe(8)
    
    response.headers.update({
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
        'Expires': '0',
        'WWW-Authenticate': f'Basic realm="Login-{timestamp}-{random_component}"',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Credentials': 'false'
    })
    return response

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username is None or password is None:
            flash('Please provide both username and password')
            return render_template('login.html')
            
        if check_auth(username, password):
            return redirect(url_for('upload'))
        else:
            flash('Invalid credentials')
            
    return render_template('login.html')

# Add this new route for reset attendance
@app.route('/reset_attendance', methods=['POST'])
@requires_auth
def reset_attendance_route():
    try:
        reset_attendance()
        flash('Attendance has been reset successfully')
    except Exception as e:
        flash(f'Error resetting attendance: {str(e)}')
    return redirect(url_for('upload'))

if __name__ == '__main__':
    init_app()
    socketio.run(app, debug=True)