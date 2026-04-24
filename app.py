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
    
    hazards = db_manager.get_all_hazards()
    
    # Filter in Python for the demo
    if h_type:
        hazards = [h for h in hazards if h['hazard_type'] == h_type]
    if severity:
        hazards = [h for h in hazards if h['confidence'] == severity]
    if location:
        hazards = [h for h in hazards if location.lower() in h['location_text'].lower()]
        
    hazards.sort(key=lambda x: x['updated_at'], reverse=True)
    return render_template('hazards.html', hazards=hazards, search_query=location)

def notify_route_users(hazard):
    # This checks if the new hazard location matches any user's travel routes
    all_users = db_manager.users_table.scan().get('Items', [])
    notified_count = 0
    
    for u in all_users:
        routes = db_manager.get_routes_for_user(u['username'])
        for route in routes:
            waypoints = [w.strip().lower() for w in route['waypoints'].split(',')]
            hazard_loc = hazard['location_text'].lower()
            is_match = any(w in hazard_loc for w in waypoints)
            
            if is_match:
                # Persistent In-App Notification
                db_manager.create_in_app_notif(
                    u['username'],
                    f"Route Alert: {hazard['hazard_type']}",
                    f"A new {hazard['hazard_type']} has been reported in {hazard['location_text']}, which intersects with your {route['route_name']} travel channel."
                )
                print(f"[INTERNAL NOTIFICATION] User {u['username']} alerted about route match.")
                notified_count += 1
                
    return notified_count

@app.route('/notifications/clear', methods=['POST'])
@app.route('/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    db_manager.clear_user_notifications(current_user.username)
    return redirect(url_for('profile'))

@app.route('/add_route', methods=['POST'])
@login_required
def add_route():
    name = request.form.get('route_name')
    waypoints = request.form.get('waypoints')
    
    if name and waypoints:
        db_manager.create_route(current_user.username, name, waypoints)
        flash(f'Travel Channel "{name}" activated. System is now monitoring this sector.', 'success')
        
    return redirect(url_for('profile'))

@app.route('/delete_route/<string:id>', methods=['POST'])
@login_required
def delete_route(id):
    db_manager.delete_route(id)
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
            flash('This alias is already assigned to another operative.', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            db_manager.create_user(username, email, hashed_password)
            
            # [AWS SNS INTEGRATION]
            # Automatically request subscription for the new user
            db_manager.subscribe_email_to_sns(email)
            
            flash('Identity verified. Welcome to the network, Operative.', 'success')
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
            if db_manager.get_user(new_username):
                flash('Username already in use.', 'danger')
                return redirect(url_for('profile'))
            # Note: Changing username in DynamoDB requires creating a new item and deleting old one
            # For this demo, we'll just update other fields
            
        if new_password:
            db_manager.update_user(current_user.username, {'password_hash': generate_password_hash(new_password)})
            
        flash('Operational credentials updated successfully.', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html')

@app.route('/update_my_hazard/<string:hazard_id>', methods=['POST'])
@login_required
def update_my_hazard(hazard_id):
    hazard = db_manager.get_hazard(hazard_id)
    
    # Security: Check if user is one of the reporters
    reports = db_manager.get_reports_for_hazard(hazard_id)
    user_report = next((r for r in reports if r.get('user_id') == current_user.username), None)
    
    if not user_report:
        flash('Operational oversight: You are not authorized to modify this node.', 'danger')
        return redirect(url_for('profile'))
        
    if hazard['status'] != 'Active':
        flash('Access Restricted: Administrative intervention is already in progress.', 'info')
        return redirect(url_for('profile'))
        
    new_status = request.form.get('status')
    if new_status in ['Resolved', 'Active']:
        db_manager.update_hazard(hazard_id, {'status': new_status})
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
    
    # Map for easy lookup
    hazard_map = {h['hazard_id']: h for h in all_hazards}
    
    total_count = len(all_hazards)
    investigating_count = len(db_manager.get_hazards_by_status('Under Investigation'))
    solved_count = len(db_manager.get_hazards_by_status('Resolved'))
    active_count = len(db_manager.get_hazards_by_status('Active'))
    
    all_reports = db_manager.get_all_reports()
    
    # Hydrate reports with hazard data
    for r in all_reports:
        r['hazard'] = hazard_map.get(r['hazard_id'], {'hazard_type': 'Unknown'})
        # Also hydrate user if needed, but username is enough
        r['user'] = {'username': r['user_id']} if r.get('user_id') else None
        
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
