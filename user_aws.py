from flask_login import UserMixin

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
