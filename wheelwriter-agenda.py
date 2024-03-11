import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import pickle
import os
from openai import OpenAI
import click
import datetime
import time
import sys
import serial
import textwrap
from pyicloud import PyiCloudService

api = PyiCloudService("icloud email", "app-specific pw")

if api.requires_2fa:
    print("Two-factor authentication required. Your trusted devices are:")

    devices = api.trusted_devices
    for i, device in enumerate(devices):
        print(
            "  %s: %s"
            % (i, device.get("deviceName", "SMS to %s" % device.get("phoneNumber")))
        )

    device = click.prompt("Which device would you like to use?", default=0)
    device = devices[device]
    if not api.send_verification_code(device):
        print("Failed to send verification code")
        sys.exit(1)

    code = click.prompt("Please enter validation code")
    if not api.validate_verification_code(device, code):
        print("Failed to verify verification code")
        sys.exit(1)

# Gmail API setup
# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/calendar.readonly']
credentials = None
if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        credentials = pickle.load(token)
if not credentials or not credentials.valid:
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        credentials = flow.run_local_server(port=0)
    with open('token.pickle', 'wb') as token:
        pickle.dump(credentials, token)

service = build('gmail', 'v1', credentials=credentials)

# Fetch emails from the past 24 hours
now = datetime.datetime.now()
yesterday = now - datetime.timedelta(days=1)
query = f'label:inbox after:{yesterday.strftime("%Y/%m/%d")} before:{now.strftime("%Y/%m/%d")}'
results = service.users().messages().list(userId='me', q=query).execute()
messages = results.get('messages', [])

emails = []
for message in messages:
    msg = service.users().messages().get(userId='me', id=message['id'], format='metadata').execute()
    headers = msg['payload']['headers']
    subject = next(header['value'] for header in headers if header['name'] == 'Subject')
    sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
    snippet = msg.get('snippet', '')
    emails.append(f"Sender: {sender}, Subject: {subject}, Preview: {snippet}")

# Build the Calendar service
calendar_service = build('calendar', 'v3', credentials=credentials)

# Calendar functionality to fetch events for the next 30 days
start_time = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
end_time = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat() + 'Z'
events_result = calendar_service.events().list(calendarId='primary', timeMin=start_time,
                                                timeMax=end_time, singleEvents=True,
                                                orderBy='startTime').execute()
events = events_result.get('items', [])

cal_list = []

for event in events:
    start = event['start'].get('dateTime', event['start'].get('date'))
    cal_list.append(f"Event: {event['summary']}, Start: {start}")

# Get today's date
today = datetime.date.today()

# Calculate the date 30 days from today
thirty_days_later = today + datetime.timedelta(days=30)

birthdays = []
for c in api.contacts.all():
    birthday_str = c.get("birthday")
    if birthday_str:
        # Extract year, month, and day from the birthday string
        year, month, day = map(int, birthday_str.split('-'))
        # Create a birthday date for this year for comparison
        # Using today.year to handle the birthday occurrence this year
        birthday_this_year = datetime.date(today.year, month, day)

        if today <= birthday_this_year <= thirty_days_later:
            birthdays.append(f"First name: {c.get('firstName')}, Birthday: {birthday_str}")

email_details = "\n".join(emails)  # Assuming `emails` contains the list of email details
cal_details = "\n".join(cal_list)
birthday_details = "\n".join(birthdays)

user_message = f"My name's Josh, and you're my executive assistant Mr. McGillicuddy. You're a little quirky and goofy. Write me a quick, concise, chipper, friendly note updating me on my agenda. Include today's date and day of the week ({today}). Wrap your headers in ANSI escape code (^[[1m and ^[[0m for bold). Be concise - time is money - but include a motivational quote. IMPORTANT: NEVER USE ANY EMOJIS OR SPECIAL CHARACTERS. Mention any important emails from the below list (ignore promotional emails, and focus on things I need to deal with):\n{email_details}\nIdentify any upcoming holidays. Mention any upcoming birthdays:\n:{birthday_details}.\n Mention any upcoming events:\n{cal_details}"

print(user_message)

# Initialize the OpenAI client
client = OpenAI(
    api_key = 'xxx'
)

# Prepare the chat messages
messages = [
    {"role": "system", "content": "You are my helpful executive assistant. You never use emoji."},
    {"role": "user", "content": user_message}
]

# Send request to OpenAI API using chat completions
response = client.chat.completions.create(
  model="gpt-4-1106-preview",  # Use the appropriate model for your use case
  messages=messages
)

# Print the response
print(response.choices[0].message.content)

def wrap_text_preserving_paragraphs(text, width):
    # Split the text into paragraphs
    paragraphs = text.split('\n\n')
    
    # Wrap each paragraph
    wrapped_paragraphs = [textwrap.fill(paragraph, width) for paragraph in paragraphs]
    
    # Join the wrapped paragraphs back together
    wrapped_text = '\n\n'.join(wrapped_paragraphs)
    
    return wrapped_text
    
textLines = wrap_text_preserving_paragraphs(response.choices[0].message.content, 80)
serialDevice = "/dev/tty.usbmodem1101"
endLines = 3
keyboard = 1
#textLines = wrappedLines.split('\n')

retryCounter = 0
characterCounter = 0
with serial.Serial(serialDevice, 115200, xonxoff=True) as ser:
    while True:
        print('\n*** Sending "\\n" ***')
        ser.write('\n'.encode());
        
        line = ser.readline().decode().strip()
        print(line)

        if line.startswith('###'):
            line = ser.readline().decode().strip()
            print(line)

        if line == '[READY]':
            break

        retryCounter += 1
        if retryCounter >= 5:
            print('\nERROR - Failed to connect!')
            sys.exit(1)
        time.sleep(1)

    print('\n*** Switching to type mode ***')
    print(f'type {keyboard}\n')
    ser.write(f'type {keyboard}\n'.encode())

    while True:
        line = ser.readline().decode().strip()
        print(line)
        if line == '[BEGIN]':
            break

    for textLine in textLines:
        for char in textLine:
            ser.write(char.encode())
            time.sleep(0.05)
            characterCounter += 1

    for i in range(endlines):
        ser.write('\n'.encode())
        time.sleep(0.05)

    print('\n*** Exiting type mode ***')
    ser.write(b'\x04')
    line = ser.readline().decode().strip()
    print(line)

print(f'\n*** Sent {characterCounter} characters ***')