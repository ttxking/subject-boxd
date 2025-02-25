from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

db = SQLAlchemy()

class User(db.Model, UserMixin):  
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.Text), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<User {self.username}>'

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=False, nullable=False)
    code = db.Column(db.String(50), nullable=False, unique=True)
    school = db.Column(db.String(200), nullable=True)
    college = db.Column(db.String(200), nullable=True)
    scqf = db.Column(db.String(50), nullable=True)
    credits = db.Column(db.String(50), nullable=True)
    availability = db.Column(db.String(200), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    assessment = db.Column(db.Text, nullable=True)
    learning_outcomes = db.Column(db.Text, nullable=True)
    total_hours = db.Column(db.Text, nullable=True)
    prerequisites = db.Column(db.Text, nullable=True)
    prohibited_combinations = db.Column(db.Text, nullable=True)
    additional_costs = db.Column(db.Text, nullable=True)
    course_organizer = db.Column(db.String(200), nullable=True)
    period = db.Column(db.String(100), nullable=True)
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<Subject {self.name}>'

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    user = db.relationship('User', backref='reviews', lazy=True)
    subject = db.relationship('Subject', backref='reviews', lazy=True)

    def __repr__(self):
        return f'<Review {self.id}>'