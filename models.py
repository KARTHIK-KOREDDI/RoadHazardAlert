from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import pytz
from datetime import datetime

db = SQLAlchemy()

def get_ist():
    # Return naive datetime representing IST for database compatibility
    return datetime.now(pytz.timezone('Asia/Kolkata')).replace(tzinfo=None)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    is_trusted = db.Column(db.Boolean, default=True) 

class Hazard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hazard_type = db.Column(db.String(50), nullable=False)
    location_lat = db.Column(db.Float, nullable=True)
    location_lon = db.Column(db.Float, nullable=True)
    location_text = db.Column(db.String(200), nullable=False)
    report_count = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='Active') 
    confidence = db.Column(db.String(10), default='Low') 
    created_at = db.Column(db.DateTime, default=get_ist)
    updated_at = db.Column(db.DateTime, default=get_ist, onupdate=get_ist)
    
    reports = db.relationship('Report', backref='hazard', lazy=True, cascade="all, delete-orphan")

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hazard_id = db.Column(db.Integer, db.ForeignKey('hazard.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_trusted = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=get_ist)
    
    user = db.relationship('User', backref='my_reports')

class SiteVisit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_ist)

class UserRoute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    route_name = db.Column(db.String(100), nullable=False)
    waypoints = db.Column(db.Text, nullable=False) 
    created_at = db.Column(db.DateTime, default=get_ist)
    
    user = db.relationship('User', backref='my_routes')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=get_ist)
    is_read = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', backref='notifications')
