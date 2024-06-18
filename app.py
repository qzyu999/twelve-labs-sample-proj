# import os
# import random
# import string
# from flask import Flask, render_template, request, redirect, url_for
# from twelvelabs import TwelveLabs
# from twelvelabs.models.task import Task

# app = Flask(__name__)

# # Twelve Labs configuration
# API_KEY = os.getenv('API_KEY')
# client = TwelveLabs(api_key=API_KEY)
# ALLOWED_EXTENSIONS = ['mp4']
# UPLOAD_FOLDER = 'static/videos'
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# def generate_unique_index_name(base_name):
#     random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
#     return f"{base_name}-{random_string}"

# @app.route('/')
# def index():
#     return render_template('index.html')

# @app.route('/upload', methods=['POST'])
# def upload():
#     if 'video' not in request.files:
#         return "No video file found"

#     video = request.files['video']
#     if video.filename == "":
#         return 'No video file selected'

#     if video and allowed_file(video.filename):
#         video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
#         video.save(video_path)

#         # Generate a unique index name based on the video's filename
#         base_name = os.path.splitext(video.filename)[0]
#         index_name = generate_unique_index_name(base_name)

#         # Create a new index with the unique name
#         index = client.index.create(
#             name=index_name,
#             engines=[
#                 {
#                     "name": "pegasus1",
#                     "options": ["visual", "conversation"],
#                 }
#             ]
#         )

#         # Upload video to Twelve Labs API
#         task = client.task.create(index_id=index.id, file=video_path, language="en")
        
#         # Wait for the task to complete
#         task.wait_for_done(sleep_interval=50)
#         if task.status != "ready":
#             return f"Indexing failed with status {task.status}"

#         video_id = task.video_id
#         return redirect(url_for('summary', video_id=video_id, video_name=video.filename))

#     return "Invalid file type"

# @app.route('/summary/<video_id>/<video_name>')
# def summary(video_id, video_name):
#     # Generate text summaries for the video
#     res_gist = client.generate.gist(video_id=video_id, types=["title", "topic", "hashtag"])
#     res_summary = client.generate.summarize(video_id=video_id, type="summary")
#     res_chapters = client.generate.summarize(video_id=video_id, type="chapter")
#     res_highlights = client.generate.summarize(video_id=video_id, type="highlight")
#     res_keywords = client.generate.text(video_id=video_id, prompt="Based on this video, I want to generate five keywords for SEO (Search Engine Optimization).")

#     return render_template(
#         'summary.html',
#         video_name=video_name,
#         title=res_gist.title,
#         topics=res_gist.topics,
#         hashtags=res_gist.hashtags,
#         summary=res_summary.summary,
#         chapters=res_chapters.chapters,
#         highlights=res_highlights.highlights,
#         keywords=res_keywords.data
#     )

# if __name__ == "__main__":
#     app.run(debug=True)


import os
import random
import string
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from twelvelabs import TwelveLabs
from twelvelabs.models.task import Task

app = Flask(__name__)

# Configure the SQLAlchemy part of the app instance to use SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///video_summaries.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Create the SQLAlchemy db instance
db = SQLAlchemy(app)

# Define the VideoSummary model
class VideoSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(5000), unique=True, nullable=False)
    video_name = db.Column(db.String(5000), nullable=False)
    title = db.Column(db.String(5000), nullable=False)
    topics = db.Column(db.String(5000), nullable=False)
    hashtags = db.Column(db.String(5000), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    chapters = db.Column(db.JSON, nullable=False)
    highlights = db.Column(db.JSON, nullable=False)
    keywords = db.Column(db.String(5000), nullable=False)

# Initialize the database only if it does not already exist
if not os.path.exists('video_summaries.db'):
    with app.app_context():
        db.create_all()

# Twelve Labs configuration
API_KEY = os.getenv('API_KEY')
client = TwelveLabs(api_key=API_KEY)
ALLOWED_EXTENSIONS = ['mp4']
UPLOAD_FOLDER = 'static/videos'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_index_name(base_name):
    random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{base_name}-{random_string}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files:
        return "No video file found"

    video = request.files['video']
    if video.filename == "":
        return 'No video file selected'

    if video and allowed_file(video.filename):
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
        video.save(video_path)

        # Generate a unique index name based on the video's filename
        base_name = os.path.splitext(video.filename)[0]
        index_name = generate_unique_index_name(base_name)

        # Create a new index with the unique name
        index = client.index.create(
            name=index_name,
            engines=[
                {
                    "name": "pegasus1",
                    "options": ["visual", "conversation"],
                }
            ]
        )

        # Upload video to Twelve Labs API
        task = client.task.create(index_id=index.id, file=video_path, language="en")
        
        # Wait for the task to complete
        task.wait_for_done(sleep_interval=50)
        if task.status != "ready":
            return f"Indexing failed with status {task.status}"

        video_id = task.video_id

        # Generate summaries and save them to the database
        res_gist = client.generate.gist(video_id=video_id, types=["title", "topic", "hashtag"])
        res_summary = client.generate.summarize(video_id=video_id, type="summary")
        res_chapters = client.generate.summarize(video_id=video_id, type="chapter")
        res_highlights = client.generate.summarize(video_id=video_id, type="highlight")
        res_keywords = client.generate.text(video_id=video_id, prompt="Based on this video, I want to generate five keywords for SEO (Search Engine Optimization).")

        video_summary = VideoSummary(
            video_id=video_id,
            video_name=video.filename,
            title=res_gist.title,
            topics=res_gist.topics,
            hashtags=res_gist.hashtags,
            summary=res_summary.summary,
            chapters=res_chapters.chapters,
            highlights=res_highlights.highlights,
            keywords=res_keywords.data
        )

        db.session.add(video_summary)
        db.session.commit()

        return redirect(url_for('summary', video_id=video_id))

    return "Invalid file type"

@app.route('/summary/<video_id>')
def summary(video_id):
    video_summary = VideoSummary.query.filter_by(video_id=video_id).first_or_404()
    return render_template(
        'summary.html',
        video_name=video_summary.video_name,
        title=video_summary.title,
        topics=video_summary.topics,
        hashtags=video_summary.hashtags,
        summary=video_summary.summary,
        chapters=video_summary.chapters,
        highlights=video_summary.highlights,
        keywords=video_summary.keywords
    )

@app.route('/history')
def history():
    summaries = VideoSummary.query.all()
    return render_template('history.html', summaries=summaries)

if __name__ == "__main__":
    app.run(debug=True)
