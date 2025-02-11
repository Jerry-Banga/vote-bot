import requests
import random
import time
import boto3
from fake_useragent import UserAgent
import logging
from logging.handlers import RotatingFileHandler

# Configure logging to log both errors and successful outputs
logging.basicConfig(
    filename="/var/log/vote_bot/gbot2.log",  # Store logs in /var/log/vote_bot/
    level=logging.INFO,  # Log all messages from INFO and above (including ERROR)
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Set up the log rotation (e.g., 10MB max file size, 5 backup files)
handler = RotatingFileHandler(
    "/var/log/vote_bot/gbot2backup.log", maxBytes=10*1024*1024, backupCount=5
)
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Add the handler to the logger
logging.getLogger().addHandler(handler)

# === CONFIGURATION ===
VOTE_URL = "https://momentofglow.shalina.com/wp-admin/admin-ajax.php"
CONTESTANT_ID = 4396
# TOTAL_VOTES = 50000  # Total votes you want to send
# DELAY_RANGE = (2, 4)  # Random delay range (seconds)
MAX_FAILURES = 10  # Shut down if remote server fails too many times
SNS_TOPIC_ARN = "arn:aws:sns:eu-west-3:664418988747:VoteNotifications"
AWS_REGION = "eu-west-3"

ua = UserAgent()
sns_client = boto3.client("sns", region_name=AWS_REGION)
ec2_client = boto3.client("ec2", region_name=AWS_REGION)

# Function to create a new session
def create_new_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": ua.random,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://momentofglow.shalina.com",
        "Referer": "https://momentofglow.shalina.com/contestants/graciella-nzuzi/",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    })
    return session

def send_sns_notification(subject, message):
    """Send an email notification via AWS SNS."""
    response = sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject=subject
    )
    logging.info(f"[📧] Notification sent: {response['MessageId']}")

def stop_ec2_instance():
    """Shut down the EC2 instance if the remote server is unresponsive."""
    instance_id = requests.get("http://169.254.169.254/latest/meta-data/instance-id").text
    logging.info(f"[⚠] Stopping EC2 instance: {instance_id}")
    send_sns_notification("Vote Bot - Shutting Down", f"EC2 instance {instance_id} is shutting down due to server issues.")
    ec2_client.stop_instances(InstanceIds=[instance_id])



# Start the first session
session = create_new_session()
vote_count = 0
failure_count = 0

while True:
    # Vote request payload
    data = {
        "action": "mog_cast_vote",
        "contestant_id": CONTESTANT_ID
    }

    try:
        response = session.post(VOTE_URL, data=data, timeout=10)  # Timeout to prevent hanging
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                logging.info(f"[✔] Vote {vote_count + 1}: Success - {result['data']['message']}")
                vote_count += 1
                failure_count = 0  # Reset failure count on success
            else:
                logging.error(f"[✖] Vote {vote_count + 1}: Failed - {result['data']['message']}")
                if "limite de votos" in result["data"]["message"]:
                    logging.info("[!] Session limit reached. Restarting session...")
                    session.close()
                    time.sleep(2)
                    session = create_new_session()

        else:
            logging.error(f"[ERROR] Request failed with status {response.status_code}")
            failure_count += 1

    except requests.exceptions.RequestException as e:
        logging.error(f"[ERROR] Network issue: {e}")
        failure_count += 1

    # Stop EC2 if server is down
    if failure_count >= MAX_FAILURES:
        logging.error("[❌] Remote server is unresponsive. Stopping EC2...")
        stop_ec2_instance()
        break


