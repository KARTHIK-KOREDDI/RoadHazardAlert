import os
import math
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from aws_db import DynamoDBManager, get_ist
from user_aws import User

app = Flask(__name__)
app.config['SECRET_KEY'] = 'road-hazard-secret-key-123'

db_manager = DynamoDBManager()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def get_now():
    return get_ist()

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id, db_manager)

def calculate_confidence(hazard):
    # In DynamoDB, we fetch reports using GSI
    reports = db_manager.get_reports_for_hazard(hazard['hazard_id'])
    
    # Filter reports from last 48 hours
    time_threshold = datetime.now() - timedelta(hours=48)
    active_reports = []
    for r in reports:
        r_time = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
        if r_time > time_threshold:
            active_reports.append(r)
    
    score = 0
    for r in active_reports:
        score += 2 if r.get('is_trusted') else 1
        
    if score >= 6:
        new_conf = 'High'
    elif score >= 3:
        new_conf = 'Medium'
    else:
        new_conf = 'Low'
        
    if new_conf == 'High' and hazard.get('confidence') != 'High':
        # [AWS SNS INTEGRATION]
        db_manager.send_sns_alert(f"High Priority Hazard Detected: {hazard['hazard_type']} at {hazard['location_text']}")
        print(f"[AWS SNS TOPIC TRIGGERED] Hazard confidence reached HIGH: {hazard['hazard_type']}")
        
    db_manager.update_hazard(hazard['hazard_id'], {
        'confidence': new_conf,
        'report_count': len(active_reports)
    })

def find_nearby_hazard(h_type, lat, lon, location_text):
    hazards = db_manager.get_all_hazards()
    threshold = 0.005 
    for h in hazards:
        if h['hazard_type'] == h_type and h['status'] == 'Active':
            if lat and lon and h.get('location_lat') and h.get('location_lon'):
                dist = math.sqrt((float(h['location_lat']) - lat)**2 + (float(h['location_lon']) - lon)**2)
                if dist < threshold:
                    return h
            elif h['location_text'] == location_text:
                return h
    return None

# --- ROUTES ---

@app.route('/')
def index():
    # Site visits tracking can be moved to DynamoDB Analytics table
    recent_hazards = db_manager.get_all_hazards()
    recent_hazards.sort(key=lambda x: x['created_at'], reverse=True)
    recent_hazards = recent_hazards[:5]
    
    total_hazards = len(db_manager.get_all_hazards())
    # Placeholder for counts that would normally be aggregated
    total_visits = 100 # Simulated
    trusted_reporters = 5 # Simulated
    
    return render_template('index.html', 
                          recent_hazards=recent_hazards,
                          total_hazards=total_hazards,
                          total_visits=total_visits,
                          trusted_reporters=trusted_reporters)

@app.route('/hazards')
def view_hazards():
    h_type = request.args.get('type')
    severity = request.args.get('severity') 
    location = request.args.get('location')
    
    query = Hazard.query
    if h_type: 
        query = query.filter(Hazard.hazard_type == h_type)
    if severity: 
        query = query.filter(Hazard.confidence == severity)
    if location: 
        # Search by text match in location_text
        query = query.filter(Hazard.location_text.ilike(f"%{location}%"))
        
    # Sort by the most recent activity (new reports/updates)
    hazards = query.order_by(Hazard.updated_at.desc()).all()
    return render_template('hazards.html', hazards=hazards, search_query=location)

def notify_route_users(hazard):
    all_routes = UserRoute.query.all()
    notified_count = 0
    
    for route in all_routes:
        waypoints = [w.strip().lower() for w in route.waypoints.split(',')]
        hazard_loc = hazard.location_text.lower()
        is_match = any(w in hazard_loc for w in waypoints)
        
        if is_match:
            # Persistent In-App Notification
            notif = Notification(
                user_id=route.user_id,
                title=f"Route Alert: {hazard.hazard_type}",
                message=f"A new {hazard.hazard_type} has been reported in {hazard.location_text}, which intersects with your {route.route_name} travel channel."
            )
            db.session.add(notif)
            
            # [AWS SNS INTEGRATION]
            print(f"\n[AWS SNS + INBOX ALERT] Target: {route.user.username} | Route: {route.route_name}")
            notified_count += 1
            
    db.session.commit()
    return notified_count

@app.route('/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for('profile'))

@app.route('/add_route', methods=['POST'])
@login_required
def add_route():
    name = request.form.get('route_name')
    waypoints = request.form.get('waypoints')
    
    if name and waypoints:
        new_route = UserRoute(user_id=current_user.id, route_name=name, waypoints=waypoints)
        db.session.add(new_route)
        db.session.commit()
        flash(f'Travel Channel "{name}" activated. System is now monitoring this sector.', 'success')
        
    return redirect(url_for('profile'))

@app.route('/delete_route/<int:id>', methods=['POST'])
@login_required
def delete_route(id):
    route = UserRoute.query.get_or_404(id)
    if route.user_id == current_user.id:
        db.session.delete(route)
        db.session.commit()
        flash('Monitoring for this sector deactivated.', 'info')
    return redirect(url_for('profile'))

@app.route('/report', methods=['GET', 'POST'])
def report_hazard():
    if request.method == 'POST':
        h_type = request.form.get('hazard_type')
        loc_text = request.form.get('location_text')
        description = request.form.get('description')
        lat = float(request.form.get('lat')) if request.form.get('lat') else None
        lon = float(request.form.get('lon')) if request.form.get('lon') else None
        
        existing = find_nearby_hazard(h_type, lat, lon, loc_text)

        if existing:
            hazard = existing
        else:
            hazard = db_manager.create_hazard(h_type, lat, lon, loc_text)
            
        is_trusted = current_user.is_authenticated
        user_id = current_user.username if is_trusted else None
        
        db_manager.create_report(hazard['hazard_id'], user_id, is_trusted, description)
        
        # Trigger Intelligent Processing
        calculate_confidence(hazard)
        # notify_route_users(hazard) # Skipping for now, can be implemented similarly
        
        flash('Report synchronized to regional AWS log.', 'success')
        return redirect(url_for('index'))
        
    return render_template('report.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if db_manager.get_user(username):
            flash('Username already registered.', 'danger')
            return redirect(url_for('register'))
            
        db_manager.create_user(username, email, generate_password_hash(password))
        flash('Registration successful. You can now login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user_data = db_manager.get_user(username)
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        
        if new_username != current_user.username:
            if User.query.filter_by(username=new_username).first():
                flash('Username already in use.', 'danger')
                return redirect(url_for('profile'))
            current_user.username = new_username
            
        if new_password:
            current_user.password_hash = generate_password_hash(new_password)
            
        db.session.commit()
        flash('Operational credentials updated successfully.', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html')

@app.route('/update_my_hazard/<int:hazard_id>', methods=['POST'])
@login_required
def update_my_hazard(hazard_id):
    hazard = Hazard.query.get_or_404(hazard_id)
    
    # Security: Check if user is one of the reporters
    user_report = Report.query.filter_by(hazard_id=hazard_id, user_id=current_user.id).first()
    
    if not user_report:
        flash('Operational oversight: You are not authorized to modify this node.', 'danger')
        return redirect(url_for('profile'))
        
    if hazard.status != 'Active':
        flash('Access Restricted: Administrative intervention is already in progress.', 'info')
        return redirect(url_for('profile'))
        
    new_status = request.form.get('status')
    if new_status in ['Resolved', 'Active']:
        hazard.status = new_status
        db.session.commit()
        flash(f'Hazard status updated to {new_status} by reporter.', 'success')
        
    return redirect(url_for('profile'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('index'))
    all_hazards = db_manager.get_all_hazards()
    total_count = len(all_hazards)
    investigating_count = len(db_manager.get_hazards_by_status('Under Investigation'))
    solved_count = len(db_manager.get_hazards_by_status('Resolved'))
    active_count = len(db_manager.get_hazards_by_status('Active'))
    
    all_reports = db_manager.get_all_reports()
    all_reports.sort(key=lambda x: x['timestamp'], reverse=True)
    detailed_reports = all_reports[:50]
    
    trusted = db_manager.get_trusted_users()
    anon = [r for r in all_reports if r.get('user_id') is None]
    today_visits = 50 # Simulated for AWS
    
    return render_template('admin.html', hazards=all_hazards, total_count=total_count, investigating_count=investigating_count, solved_count=solved_count, active_count=active_count, detailed_reports=detailed_reports, trusted_reporters=trusted, anonymous_reports=anon, daily_visits=today_visits)

@app.route('/admin/update_hazard/<string:id>', methods=['POST'])
@login_required
def update_hazard(id):
    if not current_user.is_admin: return jsonify({'error': 'Unauthorized'}), 403
    new_status = request.form.get('status')
    if new_status:
        db_manager.update_hazard(id, {'status': new_status})
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_hazard/<string:id>', methods=['POST'])
@login_required
def delete_hazard(id):
    if not current_user.is_admin: return jsonify({'error': 'Unauthorized'}), 403
    db_manager.delete_hazard(id)
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
