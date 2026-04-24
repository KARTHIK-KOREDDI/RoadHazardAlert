from aws_db import DynamoDBManager
from werkzeug.security import generate_password_hash

def create_admin():
    db_manager = DynamoDBManager()
    admin = db_manager.get_user('admin')
    if not admin:
        db_manager.create_user(
            username='admin',
            email='admin@roadalert.com',
            password_hash=generate_password_hash('adminpassword123'),
            is_admin=True
        )
        print("Admin user 'admin' created in DynamoDB with password 'adminpassword123'")
    else:
        print("Admin user already exists in DynamoDB.")

if __name__ == "__main__":
    create_admin()
