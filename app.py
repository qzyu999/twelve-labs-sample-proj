import os
import random
import string
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from filters import seconds_to_hhmmss
from sqlalchemy.types import TypeDecorator, TEXT
from twelvelabs import TwelveLabs
from twelvelabs.exceptions import APIConnectionError, APIError

# Twelve Labs configuration
API_KEY = os.getenv('API_KEY')
client = TwelveLabs(api_key=API_KEY)
ALLOWED_EXTENSIONS = ['mp4']
UPLOAD_FOLDER = 'static/videos'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'supersecretkey'  # Needed for flashing messages

# Configure the SQLAlchemy part of the app instance to use SQLite
db_path = os.path.join(os.getcwd(), 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Create the SQLAlchemy db instance
db = SQLAlchemy(app)

# Define your models here
class JSONType(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, default=lambda o: o.__dict__)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None

class VideoSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(200), nullable=False)
    index_name = db.Column(db.String(1000), nullable=False)
    video_name = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    topics = db.Column(JSONType, nullable=False)
    hashtags = db.Column(JSONType, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    chapters = db.Column(JSONType, nullable=False)  # Store as JSON string
    highlights = db.Column(JSONType, nullable=False)  # Store as JSON string
    keywords = db.Column(JSONType, nullable=False)

# Initialize the database only if it does not already exist
if not os.path.exists(db_path):
    with app.app_context():
        db.create_all()

# Register the custom filter with Jinja2
app.jinja_env.filters['seconds_to_hhmmss'] = seconds_to_hhmmss

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
        flash("No video file found")
        return redirect(url_for('index'))

    video = request.files['video']
    if video.filename == "":
        flash('No video file selected')
        return redirect(url_for('index'))

    if video and allowed_file(video.filename):
        try:
            # Generate a unique index name based on the video's filename
            base_name, ext = os.path.splitext(video.filename)
            index_name = generate_unique_index_name(base_name)

            # Save the video file to the upload folder
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
            video.save(video_path)

            # Upload video to Twelve Labs API
            index = client.index.create(
                name=index_name,
                engines=[
                    {
                        "name": "pegasus1",
                        "options": ["visual", "conversation"],
                    }
                ]
            )
            task = client.task.create(index_id=index.id, file=video_path, language="en")
            task.wait_for_done(sleep_interval=50)

            if task.status != "ready":
                flash(f"Indexing failed with status {task.status}")
                return redirect(url_for('index'))

            video_id = task.video_id

            # Generate summaries and save them to the database
            res = client.generate.gist(video_id=video_id, types=["title", "topic", "hashtag"])
            res_title = res.title
            res_topics = res.topics
            res_hashtags = res.hashtags
            res = client.generate.summarize(video_id=video_id, type="summary")
            res_summary = res.summary
            res_chapters = client.generate.summarize(video_id=video_id, type="chapter")
            res = client.generate.summarize(video_id=video_id, type="highlight")
            res_highlights = res.highlights
            res = client.generate.text(
                video_id=video_id,
                prompt="\
                    Discuss the symbolism and themes present in this music video. \
                    What are the underlying messages or motifs, and how are they represented visually and musically?"
            )
            res_keywords = res.data

            video_summary = VideoSummary(
                video_id=video_id,
                index_name=index_name,
                video_name=video.filename,
                title=res_title,
                topics=res_topics,
                hashtags=res_hashtags,
                summary=res_summary,
                chapters=res_chapters.chapters,
                highlights=res_highlights,
                keywords=res_keywords
            )

            db.session.add(video_summary)
            db.session.commit()

            return redirect(url_for('summary', video_id=video_id))

        except APIConnectionError as e:
            flash(f"API Connection Error: {e}")
            app.logger.error(f"API Connection Error: {e}")

        except APIError as e:
            flash(f"API Error: {e}")
            app.logger.error(f"API Error: {e}")

        except Exception as e:
            flash(f"An error occurred: {e}")
            app.logger.error(f"Unexpected Error: {e}")

    else:
        flash("Invalid file type")

    return redirect(url_for('index'))

@app.route('/summary/<video_id>/')
def summary(video_id):
    video_summary = VideoSummary.query.filter_by(video_id=video_id).first_or_404()
    return render_template(
        'summary.html',
        video_name=video_summary.video_name,
        index_name=video_summary.index_name,
        title=video_summary.title,
        topics=video_summary.topics,
        hashtags=video_summary.hashtags,
        summary=video_summary.summary,
        chapters=video_summary.chapters,
        highlights=video_summary.highlights,
        keywords=video_summary.keywords
    )

@app.route('/history', methods=['GET', 'POST'])
def history():
    if request.method == 'POST':
        selected_video_id = request.form.get('video_id')
        if selected_video_id:
            # Query all results for the selected video_id
            results = VideoSummary.query.filter_by(video_id=selected_video_id).all()
            return render_template('history_results.html', results=results)

    # Query all video indices and titles from the database
    video_list = VideoSummary.query.with_entities(VideoSummary.video_id, VideoSummary.video_name).all()
    return render_template('history.html', video_list=video_list)

if __name__ == "__main__":
    app.run(debug=True)
