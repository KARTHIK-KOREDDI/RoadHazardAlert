import boto3
from boto3.dynamodb.conditions import Key, Attr
import uuid
from datetime import datetime
import pytz

def get_ist():
    return datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')

class DynamoDBManager:
    def __init__(self, region='us-east-1'):
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.users_table = self.dynamodb.Table('RoadHazard_Users')
        self.hazards_table = self.dynamodb.Table('RoadHazard_Hazards')
        self.reports_table = self.dynamodb.Table('RoadHazard_Reports')
        self.routes_table = self.dynamodb.Table('RoadHazard_Routes')
        self.notifs_table = self.dynamodb.Table('RoadHazard_Notifications')
        self.sns = boto3.client('sns', region_name=region)

    # --- User Operations ---
    def get_user(self, username):
        response = self.users_table.get_item(Key={'username': username})
        return response.get('Item')

    def create_user(self, username, email, password_hash, is_admin=False):
        self.users_table.put_item(Item={
            'username': username,
            'email': email,
            'password_hash': password_hash,
            'is_admin': is_admin,
            'is_trusted': True,
            'user_id': str(uuid.uuid4())
        })

    # --- Hazard Operations ---
    def create_hazard(self, h_type, lat, lon, location_text):
        h_id = str(uuid.uuid4())
        item = {
            'hazard_id': h_id,
            'hazard_type': h_type,
            'location_lat': str(lat) if lat else None,
            'location_lon': str(lon) if lon else None,
            'location_text': location_text,
            'status': 'Active',
            'confidence': 'Low',
            'report_count': 1,
            'created_at': get_ist(),
            'updated_at': get_ist()
        }
        self.hazards_table.put_item(Item=item)
        return item

    def get_hazard(self, h_id):
        return self.hazards_table.get_item(Key={'hazard_id': h_id}).get('Item')

    def get_all_hazards(self):
        return self.hazards_table.scan().get('Items', [])

    def update_hazard(self, h_id, updates):
        update_expr = "set " + ", ".join(f"{k}=:{k}" for k in updates.keys())
        attr_values = {f":{k}": v for k, v in updates.items()}
        update_expr += ", updated_at=:updated_at"
        attr_values[":updated_at"] = get_ist()
        
        self.hazards_table.update_item(
            Key={'hazard_id': h_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=attr_values
        )

    # --- Report Operations ---
    def create_report(self, h_id, user_id, is_trusted, description):
        r_id = str(uuid.uuid4())
        item = {
            'report_id': r_id,
            'hazard_id': h_id,
            'user_id': user_id,
            'is_trusted': is_trusted,
            'description': description,
            'timestamp': get_ist()
        }
        self.reports_table.put_item(Item=item)
        return item

    def get_reports_for_hazard(self, h_id):
        response = self.reports_table.query(
            IndexName='HazardIndex',
            KeyConditionExpression=Key('hazard_id').eq(h_id)
        )
        return response.get('Items', [])

    # --- Notification Operations ---
    def send_sns_alert(self, message):
        try:
            topic_arn = self.sns.create_topic(Name='RoadHazardAlerts')['TopicArn']
            self.sns.publish(TopicArn=topic_arn, Message=message, Subject="Road Hazard Alert")
        except Exception as e:
            print(f"SNS Error: {e}")

    def update_user(self, username, updates):
        update_expr = "set " + ", ".join(f"{k}=:{k}" for k in updates.keys())
        attr_values = {f":{k}": v for k, v in updates.items()}
        self.users_table.update_item(
            Key={'username': username},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=attr_values
        )

    def create_in_app_notif(self, user_id, title, message):
        self.notifs_table.put_item(Item={
            'notif_id': str(uuid.uuid4()),
            'user_id': user_id,
            'title': title,
            'message': message,
            'timestamp': get_ist(),
            'is_read': False
        })

    def get_hazards_by_status(self, status):
        response = self.hazards_table.scan(FilterExpression=Attr('status').eq(status))
        return response.get('Items', [])

    def get_all_reports(self):
        return self.reports_table.scan().get('Items', [])

    def get_trusted_users(self):
        response = self.users_table.scan(FilterExpression=Attr('is_trusted').eq(True) & Attr('is_admin').eq(False))
        return response.get('Items', [])

    def delete_hazard(self, h_id):
        self.hazards_table.delete_item(Key={'hazard_id': h_id})
