from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///subjects.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Routes
@app.route('/')
def home():
    subjects = Subject.query.all()
    return render_template('home.html', subjects=subjects)

@app.route('/subject/<int:subject_id>')
def subject_page(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    reviews = Review.query.filter_by(subject_id=subject_id).all()
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(subject_id=subject_id).scalar()
    return render_template('subject.html', subject=subject, reviews=reviews, avg_rating=avg_rating)

@app.route('/add_review/<int:subject_id>', methods=['POST'])
def add_review(subject_id):
    data = request.form
    new_review = Review(
        user_id=int(data['user_id']),
        subject_id=subject_id,
        rating=int(data['rating']),
        comment=data['comment']
    )
    db.session.add(new_review)
    db.session.commit()
    return jsonify({"message": "Review added successfully!"}), 201

@app.route('/feed')
def feed():
    recent_reviews = Review.query.order_by(Review.created_at.desc()).limit(10).all()
    trending_subject_ids = {review.subject_id for review in recent_reviews}
    subjects = Subject.query.filter(Subject.id.in_(trending_subject_ids)).all()
    return render_template('feed.html', subjects=subjects)

if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')
    # Create database tables within app context
    with app.app_context():
        db.create_all()

    app.run(debug=True)
