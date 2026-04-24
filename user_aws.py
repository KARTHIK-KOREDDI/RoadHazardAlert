from flask_login import UserMixin
from aws_db import db_manager

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data.get('username') # Using username as ID for simplicity in DynamoDB
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password_hash')
        self.is_admin = user_data.get('is_admin', False)
        self.is_trusted = user_data.get('is_trusted', True)

    @staticmethod
    def get(username, db_manager):
        user_data = db_manager.get_user(username)
        if user_data:
            return User(user_data)
        return None

    @property
    def my_reports(self):
        reports = db_manager.get_reports_for_user(self.username)
        # Hydrate with hazard data
        all_hazards = db_manager.get_all_hazards()
        h_map = {h['hazard_id']: h for h in all_hazards}
        for r in reports:
            r['hazard'] = h_map.get(r['hazard_id'], {'hazard_type': 'Unknown', 'status': 'Unknown'})
        return reports

    @property
    def my_routes(self):
        routes = db_manager.get_routes_for_user(self.username)
        # Hydrate with hazard data
        all_hazards = db_manager.get_all_hazards()
        h_map = {h['hazard_id']: h for h in all_hazards}
        for r in routes:
            r['hazard'] = h_map.get(r['hazard_id'], {'hazard_type': 'Unknown', 'status': 'Unknown'})
        return routes
