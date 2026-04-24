import boto3
import time

def setup_aws_infra():
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1') # Change region as needed
    sns = boto3.client('sns', region_name='us-east-1')

    print("--- Provisioning DynamoDB Tables ---")
    
    tables = [
        {
            'TableName': 'RoadHazard_Users',
            'KeySchema': [{'AttributeName': 'username', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'username', 'AttributeType': 'S'}]
        },
        {
            'TableName': 'RoadHazard_Hazards',
            'KeySchema': [{'AttributeName': 'hazard_id', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': 'hazard_id', 'AttributeType': 'S'}]
        },
        {
            'TableName': 'RoadHazard_Reports',
            'KeySchema': [{'AttributeName': 'report_id', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'report_id', 'AttributeType': 'S'},
                {'AttributeName': 'hazard_id', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'HazardIndex',
                    'KeySchema': [{'AttributeName': 'hazard_id', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        },
        {
            'TableName': 'RoadHazard_Routes',
            'KeySchema': [{'AttributeName': 'route_id', 'KeyType': 'HASH'}],
            'AttributeDefinitions': [
                {'AttributeName': 'route_id', 'AttributeType': 'S'},
                {'AttributeName': 'user_id', 'AttributeType': 'S'}
            ],
            'GlobalSecondaryIndexes': [
                {
                    'IndexName': 'UserIndex',
                    'KeySchema': [{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
                }
            ]
        }
    ]

    for table_cfg in tables:
        try:
            table = dynamodb.create_table(
                TableName=table_cfg['TableName'],
                KeySchema=table_cfg['KeySchema'],
                AttributeDefinitions=table_cfg['AttributeDefinitions'],
                GlobalSecondaryIndexes=table_cfg.get('GlobalSecondaryIndexes', []),
                ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            )
            print(f"Creating {table_cfg['TableName']}...")
        except dynamodb.meta.client.exceptions.ResourceInUseException:
            print(f"Table {table_cfg['TableName']} already exists.")

    print("\n--- Provisioning SNS Topic ---")
    topic = sns.create_topic(Name='RoadHazardAlerts')
    print(f"Topic Created: {topic['TopicArn']}")

if __name__ == "__main__":
    setup_aws_infra()
