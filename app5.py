from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import requests
import re
from apscheduler.schedulers.background import BackgroundScheduler
import json
import time
import os


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ============================================================
#                     GUPSHUP CONFIG
# ============================================================


GUPSHUP_APP_NAME = "LifestyleShauryaFitnessBot"
GUPSHUP_SOURCE_NUMBER = "919911426467"
GUPSHUP_SEND_URL = "https://api.gupshup.io/wa/api/v1/msg"
GUPSHUP_API_KEY = os.environ.get("GUPSHUP_API_KEY")
OWNER_NUMBER = os.environ.get("OWNER_NUMBER")


# ============================================================
#                     GYM CONFIG
# ============================================================

GYM_NAME = "Lifestyle Shaurya Fitness Club"

INSTAGRAM_LINK = "https://www.instagram.com/shauryafitness_club_2.0?igsh=MXprMzB2NjB2NjU4"

FEES_TEXT = """💰 *Membership Plans - Lifestyle Shaurya Fitness Club*

🗓 1 Month: ₹1200
🗓 3 Months: ₹3000
🗓 6 Months: ₹5000
🗓 12 Months: ₹7000

🎁 Free Trial Available (Limited Slots)

👉 Kya main aapke liye free trial book kar du? 😊
Reply: *TRIAL*
"""

TIMINGS_TEXT = """⏰ *Gym Timings*

We’re open *daily* from -   
☀️ 5:00 AM  to 10:00 PM 🌙

Reply *MENU* to see options again 😊
"""

LOCATION_TEXT = """📍 *Lifestyle Shaurya Fitness Club Location*

A.V.R Murati, F/1B HIG, Duplex,
Sector 23, Sanjay Nagar,
Ghaziabad, Uttar Pradesh 201017

🗺 Open in Google Maps:
https://maps.app.goo.gl/oCak58keP3mBSSNPA?g_st=aw

Reply *MENU* to see options again 😊
"""

REVIEW_LINK = "https://share.google/VS4LLx4QpqOpmMA2c"

REVIEW_TEXT = f"""⭐ *Google Review Request*

Thank you for visiting *{GYM_NAME}* 💪

Aapka 30 seconds ka review hamare liye bahut valuable hai 🙏

👉 Please leave your review here:
{REVIEW_LINK}

Reply *MENU* to see options again 😊
"""

WELCOME_TEXT = f"""👋 Hi! Welcome to *{GYM_NAME}* 💪
Main aapka virtual assistant hoon 🤖

Main aapko fees, timings, free trial aur location ke baare me help kar sakta hoon.

📸 Check our Instagram:
{INSTAGRAM_LINK}

Please choose an option 👇
"""

TRANSFORMATION_IMAGES = [
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771342988/t1_zerzdm.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771343067/t2_o6dkpz.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771613371/WhatsApp_Image_2026-02-21_at_12.17.59_AM_sqgtu2.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771613496/WhatsApp_Image_2026-02-21_at_12.17.60_AM_oyc1qy.jpg"
]

GYM_IMAGES = [
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771353425/gymimg1_azqt9p.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771353463/gymimg2_fzaoo7.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771354145/gymimg3_tsuz0x.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771354563/gymimg6_i3uxmb.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771354849/gymimg4_dm3va9.jpg",
    "https://res.cloudinary.com/dgsd4mcts/image/upload/v1771356698/gymimg5_sqojxm.jpg"
]


# ============================================================
#                    GOOGLE SHEETS SETUP
# ============================================================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ.get("GOOGLE_CREDS_JSON"))
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Gym leads").sheet1

# ============================================================
#                     SESSION MEMORY
# ============================================================

user_sessions = {}

# ============================================================
#                     SCHEDULER
# ============================================================

scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

scheduled_jobs = {}
last_processed = {}
# ============================================================
#                     HELPERS
# ============================================================

def now_str():
    return datetime.now().strftime("%d-%m-%Y %H:%M")


def clean_number(num):
    if not num:
        return ""
    num = str(num)
    num = num.replace("whatsapp:", "").replace("+", "").strip()
    num = re.sub(r"\D", "", num)
    return num


def extract_name(text):
    text = text.strip()
    match = re.search(r"(my name is|i am|this is|mera naam|mein)\s+(.+)", text, re.IGNORECASE)
    if match:
        return match.group(2).strip().title()
    return text.title()


def get_session(user_id):
    user_id = clean_number(user_id)

    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "state": "MENU",
            "lead": {},
            "last_seen": datetime.now()
        }

    return user_sessions[user_id]


def lead_scoring(message):
    msg = message.lower()

    cold_words = ["test", "testing", "just checking", "wrong", "mistake", "ignore"]
    hot_words = ["fees", "price", "membership", "join", "trial", "visit", "location", "timing", "book"]

    if any(w in msg for w in cold_words):
        return "COLD"

    score = sum(1 for w in hot_words if w in msg)

    if score >= 2:
        return "HOT"
    elif score == 1:
        return "WARM"
    else:
        return "COLD"


def find_row_by_phone(phone):
    phone = clean_number(phone)

    try:
        all_rows = sheet.get_all_values()

        for i in range(1, len(all_rows)):
            if len(all_rows[i]) > 0 and clean_number(all_rows[i][0]) == phone:
                return i + 1

        return None

    except Exception as e:
        print("❌ Error finding row:", e)
        return None


def save_or_update_lead(phone, name="", interest="", lead_type="COLD", trial_status="", last_message=""):
    phone = clean_number(phone)

    try:
        row = find_row_by_phone(phone)

        if row:
            sheet.update_cell(row, 2, name)
            sheet.update_cell(row, 3, interest)
            sheet.update_cell(row, 4, lead_type)
            sheet.update_cell(row, 5, trial_status)
            sheet.update_cell(row, 6, last_message)
            sheet.update_cell(row, 7, now_str())
            print(f"✅ Updated lead row for {phone}")

        else:
            sheet.append_row([
                phone,
                name,
                interest,
                lead_type,
                trial_status,
                last_message,
                now_str()
            ])
            print(f"🎯 New lead saved for {phone}")

    except Exception as e:
        print("❌ Error saving lead:", e)


# ============================================================
#                 GUPSHUP SEND FUNCTIONS
# ============================================================

def gupshup_send_text(to, text):
    to = clean_number(to)

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    msg = json.dumps({
        "type": "text",
        "text": text
    })

    payload = {
        "channel": "whatsapp",
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": to,
        "message": msg,
        "src.name": GUPSHUP_APP_NAME
    }

    r = requests.post(GUPSHUP_SEND_URL, headers=headers, data=payload)
    print("📤 SEND TEXT:", r.status_code, r.text)
    return r.text


def gupshup_send_image(to, image_url, caption=""):
    to = clean_number(to)

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    msg = {
        "type": "image",
        "originalUrl": image_url,
        "previewUrl": image_url,
        "caption": caption
    }

    payload = {
        "channel": "whatsapp",
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": to,
        "message": json.dumps(msg),
        "src.name": GUPSHUP_APP_NAME
    }

    r = requests.post(GUPSHUP_SEND_URL, headers=headers, data=payload)
    print("📤 SEND IMAGE:", r.status_code, r.text)
    return r.text

def gupshup_send_trial_buttons(to, name):
    to = clean_number(to)

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    msg = {
        "type": "quick_reply",
        "content": {
            "type": "text",
            "text": f"Nice {name} 😊\nAap kab visit karna chahoge?"
        },
        "options": [
            {"title": "📅 Today", "postbackText": "visit_today"},
            {"title": "📅 Tomorrow", "postbackText": "visit_tomorrow"},
            {"title": "📅 Some Other Day", "postbackText": "visit_other"}
        ]
    }

    payload = {
        "channel": "whatsapp",
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": to,
        "message": json.dumps(msg),
        "src.name": GUPSHUP_APP_NAME
    }

    r = requests.post(GUPSHUP_SEND_URL, headers=headers, data=payload)
    print("📤 TRIAL BUTTONS:", r.status_code, r.text)
    return r.text



def gupshup_send_buttons(to):
    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    msg = {
        "type": "quick_reply",
        "content": {
            "type": "text",
            "text": WELCOME_TEXT
        },
        "options": [
            {"title": "💰 Fees", "postbackText": "FEES"},
            {"title": "🎁 Free Trial", "postbackText": "TRIAL"},
            {"title": "⏰ Timings", "postbackText": "TIMINGS"}
        ]
    }

    payload = {
        "channel": "whatsapp",
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": clean_number(to),
        "message": json.dumps(msg),
        "src.name": GUPSHUP_APP_NAME
    }

    r = requests.post(GUPSHUP_SEND_URL, headers=headers, data=payload)
    print("📤 QUICK REPLY MENU:", r.status_code, r.text)
    return r.text


def gupshup_send_buttons_2(to):
    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    msg = {
        "type": "quick_reply",
        "content": {
            "type": "text",
            "text": "More options 👇"
        },
        "options": [
            {"title": "📍 Location", "postbackText": "LOCATION"},
            {"title": "🔥 Transformations", "postbackText": "TRANSFORM"},
            {"title": "🏋️ Gym Photos", "postbackText": "GYM_PHOTOS"}
        ]
    }

    payload = {
        "channel": "whatsapp",
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": clean_number(to),
        "message": json.dumps(msg),
        "src.name": GUPSHUP_APP_NAME
    }

    r = requests.post(GUPSHUP_SEND_URL, headers=headers, data=payload)
    print("📤 QUICK REPLY MENU2:", r.status_code, r.text)
    return r.text


GUPSHUP_TEMPLATE_URL = "https://api.gupshup.io/wa/api/v1/template/msg"

def gupshup_send_template(to, template_id, params=None):
    to = clean_number(to)

    if params is None:
        params = []

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    payload = {
        "source": clean_number(GUPSHUP_SOURCE_NUMBER),
        "destination": to,
        "template": json.dumps({
            "id": template_id,
            "params": params
        })
    }

    try:
        r = requests.post(GUPSHUP_TEMPLATE_URL, headers=headers, data=payload)
        print("📤 TEMPLATE STATUS:", r.status_code)
        print("📤 TEMPLATE RESPONSE:", r.text)
        return r.text
    except Exception as e:
        print("❌ TEMPLATE ERROR:", e)
        return None

def notify_owner(text):
    gupshup_send_text(OWNER_NUMBER, text)


def gupshup_send_review_template(to, name):
    to = clean_number(to)

    headers = {
        "apikey": GUPSHUP_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    payload = {
        "source": GUPSHUP_SOURCE_NUMBER,
        "destination": to,
        "template": json.dumps({
            "id": "db504bec-4dd8-4f04-978c-4ddaea2ca0c6",   # replace with EXACT template id
            "params": [name, REVIEW_LINK]     # {{1}} name, {{2}} link
        })
    }

    r = requests.post(
        "https://api.gupshup.io/wa/api/v1/template/msg",
        headers=headers,
        data=payload
    )

    print("📤 REVIEW TEMPLATE:", r.status_code, r.text)
    return r.text










# ============================================================
#                     FOLLOWUP / REMINDER
# ============================================================

def followup_message(phone):
    phone = clean_number(phone)

    text = f"""👋 Hi! Quick follow-up from *{GYM_NAME}* 💪

Aap membership / free trial ke liye interested the 😊

Agar aap chahein toh main free trial slot book kar sakta hoon.

Reply *TRIAL* to book."""
    gupshup_send_text(phone, text)


def reminder_message(phone, name=""):
    phone = clean_number(phone)

    # Send approved template
    gupshup_send_template(
        phone,
        "09d6c1db-a107-4621-8543-4a7a608c9919",
        [name]   # {{1}} variable
    )

def reminder_checker():

    print("🔄 Checking reminders...")

    rows = sheet.get_all_values()
    if not rows or len(rows) < 2:
        return
    now = datetime.now()

    for i in range(1, len(rows)):

        try:
            # Safety check (very important)
            if len(rows[i]) < 11:
                continue

            phone = clean_number(rows[i][0])
            if not phone:
                continue
            reminder_time = rows[i][7]
            reminder_sent = rows[i][8]
            review_time = rows[i][9]
            review_sent = rows[i][10]

            # ================= REMINDER CHECK =================
            if reminder_time and reminder_sent == "NO":

                reminder_dt = datetime.strptime(reminder_time.strip(), "%Y-%m-%d %H:%M")

                if now >= reminder_dt:
                    name = rows[i][1]

                    reminder_message(phone, name)

                    sheet.update_cell(i+1, 9, "YES")  # ReminderSent
                    print(f"✅ Reminder sent to {phone}")

            # ================= REVIEW CHECK =================
            if review_time and review_sent == "NO":

                review_dt = datetime.strptime(review_time.strip(), "%Y-%m-%d %H:%M")

                if now >= review_dt:
                    name = rows[i][1]

                    gupshup_send_review_template(phone, name)

                    sheet.update_cell(i+1, 11, "YES")  # ReviewSent
                    print(f"⭐ Review sent to {phone}")

        except Exception as e:
            print("Reminder loop error:", e)
scheduler.add_job(reminder_checker, "interval", minutes=5)
# ============================================================
#                     BOT LOGIC
# ============================================================

def process_message(user_phone, user_message, button_id=None):

    user_phone = clean_number(user_phone)
    session = get_session(user_phone)
    state = session["state"]
    lead = session["lead"]
    print("CURRENT STATE:", state)

    msg = user_message.lower().strip() if user_message else ""

    if button_id:
        msg = button_id.lower().strip()

    lead_type = lead_scoring(msg)

    # If inside trial flow → HOT
    if state in ["ASK_NAME", "ASK_VISIT_TIME"]:
        lead_type = "HOT"

    # If user asked important business info → minimum WARM
    if any(word in msg for word in ["fees", "timings", "location", "review", "transform"]):
        if lead_type == "COLD":
            lead_type = "WARM"

    lead["lead_type"] = lead_type

    # ================= OWNER NOTIFICATION =================
    try:
        owner_msg = f"""🔔 New Lead Activity

📱 Phone: {user_phone}
💬 Message: {user_message}
🔥 Lead Type: {lead_type}
⏰ Time: {now_str()}
"""
        notify_owner(owner_msg)
    except Exception as e:
        print("Owner notification error:", e)

    # Save/update lead
    save_or_update_lead(
        phone=user_phone,
        name=lead.get("name", ""),
        interest=lead.get("interest", ""),
        lead_type=lead_type,
        trial_status=lead.get("trial_status", ""),
        last_message=user_message
    )

    # ==========================================================
    # ===================== TRIAL FLOW =========================
    # ==========================================================

    if msg in ["trial", "free trial", "book trial"]:
        session["state"] = "ASK_NAME"
        lead["interest"] = "Free Trial"
        return {"type": "text", "text": "Great! 💪 Aapka naam kya hai?"}

    if session["state"] == "ASK_NAME":
        lead["name"] = extract_name(user_message)
        session["state"] = "ASK_VISIT_TIME"
        return {
            "type": "trial_buttons",
            "name": lead["name"]
        }

    if session["state"] == "ASK_VISIT_TIME":

        if msg in ["visit_today", "today", "1"]:
            lead["visit_time"] = "Today"
        elif msg in ["visit_tomorrow", "tomorrow", "2"]:
            lead["visit_time"] = "Tomorrow"
        elif msg in ["visit_other", "other", "some other day"]:
            lead["visit_time"] = "Some Other Day"
        else:
            return {"type": "text", "text": "⚠️ Please select from given buttons."}

        lead["trial_status"] = f"Trial booked - {lead['visit_time']}"

        # Set reminder delays
        if lead["visit_time"] == "Today":
            reminder_delay = 1
            review_delay = 48
        elif lead["visit_time"] == "Tomorrow":
            reminder_delay = 16
            review_delay = 72
        else:
            reminder_delay = 48
            review_delay = 168

        reminder_time = (datetime.now() + timedelta(hours=reminder_delay)).strftime("%Y-%m-%d %H:%M")
        review_time = (datetime.now() + timedelta(hours=review_delay)).strftime("%Y-%m-%d %H:%M")

        save_or_update_lead(
            phone=user_phone,
            name=lead.get("name", ""),
            interest="Free Trial Booking",
            lead_type="HOT",
            trial_status=lead["trial_status"],
            last_message="Trial booked"
        )

        # Update sheet reminder columns
        row = find_row_by_phone(user_phone)
        if row:
            sheet.update_cell(row, 8, reminder_time)
            sheet.update_cell(row, 9, "NO")
            sheet.update_cell(row, 10, review_time)
            sheet.update_cell(row, 11, "NO")

        # Owner trial notification
        try:
            owner_trial_msg = f"""🔥 TRIAL BOOKED!

👤 Name: {lead.get("name","")}
📱 Phone: {user_phone}
📅 Visit: {lead.get("visit_time")}
⏰ Time: {now_str()}
"""
            notify_owner(owner_trial_msg)
        except Exception as e:
            print("Owner trial notify error:", e)

        session["state"] = "MENU"

        return {
            "type": "text",
            "text": f"""✅ Thanks {lead.get("name","")}!

Your free trial request has been received 💪  
Our team from *{GYM_NAME}* will contact you soon.

📌 Reminder: Your slot will be reserved for 48 hours.

Reply *MENU* anytime for options."""
        }

    # ==========================================================
    # ======================== MENU =============================
    # ==========================================================

    if msg in ["hi", "hello", "hey", "menu", "start", "or bhai"]:
        session["state"] = "MENU"

        if not session.get("welcome_sent"):
            session["welcome_sent"] = True
            return {"type": "menu"}

        return {"type": "menu_repeat"}

    # ==========================================================
    # ==================== INFORMATION =========================
    # ==========================================================

    if any(word in msg for word in ["fees", "fee", "price", "membership", "plans"]):
        lead["interest"] = "Fees"
        return {"type": "text", "text": FEES_TEXT}

    if any(word in msg for word in ["timings", "timing", "time", "open"]):
        lead["interest"] = "Timings"
        return {"type": "text", "text": TIMINGS_TEXT}

    if any(word in msg for word in ["location", "address", "where", "jagah"]):
        lead["interest"] = "Location"
        return {"type": "text", "text": LOCATION_TEXT}

    if "review" in msg:
        lead["interest"] = "Review"
        return {"type": "text", "text": REVIEW_TEXT}

    if any(word in msg for word in ["photo", "image", "photos", "images"]):
        lead["interest"] = "Gym Photos"
        return {"type": "gym_images"}

    if any(word in msg for word in ["transform", "result"]):
        lead["interest"] = "Transformations"
        return {"type": "transformations"}

    # ==========================================================
    # ==================== YES CONFIRMATION ====================
    # ==========================================================

    if msg in ["yes", "confirm_visit", "confirm"]:

        if not lead.get("trial_status", "").startswith("Trial booked"):
            return {"type": "text", "text": "🙂 Please type MENU to see options."}

        lead["trial_status"] = "Trial Confirmed"

        save_or_update_lead(
            phone=user_phone,
            name=lead.get("name", ""),
            interest=lead.get("interest", ""),
            lead_type="HOT",
            trial_status="Trial Confirmed",
            last_message="Visit Confirmed via Reminder"
        )

        try:
            owner_confirm_msg = f"""✅ TRIAL CONFIRMED!

👤 Name: {lead.get("name","")}
📱 Phone: {user_phone}
⏰ Time: {now_str()}
"""
            notify_owner(owner_confirm_msg)
        except Exception as e:
            print("Owner confirm notify error:", e)

        return {
            "type": "text",
            "text": f"""✅ Great {lead.get("name","")}!

Your visit has been successfully confirmed 💪🔥

We look forward to seeing you at *{GYM_NAME}*.

If you need any help, just type MENU 😊"""
        }

    # ==========================================================
    # ======================== FALLBACK ========================
    # ==========================================================

    return {
        "type": "text",
        "text": "⚠️ Please select a valid option.\n\nType MENU to see options."
    }

# Default fallback
    # else:
    #     return {"type": "text", "text": "🙂 Please tap buttons or type MENU to see options."}
# ============================================================
#                WEBSITE CHAT ENDPOINT
# ============================================================

@app.route("/chat", methods=["POST", "GET", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return "", 200

    if request.method == "GET":
        return "Chat endpoint is working. Use POST.", 200

    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"reply": "⚠️ No message received"}), 400

    user_message = data["message"].strip()

    user_id = "website_user"
    result = process_message(user_id, user_message)

    if result["type"] == "menu":
        return jsonify({"reply": WELCOME_TEXT})

    return jsonify({"reply": result["text"]})

# ============================================================
#                GUPSHUP WEBHOOK (FORMAT v2)
# ============================================================

@app.route("/gupshup-webhook", methods=["POST"])
def gupshup_webhook():

    # Gupshup sends JSON
    data = request.get_json(silent=True)
    print("📩 FULL DATA RECEIVED:", data)


    if not data:
        return "No JSON received", 200
    # Ignore delivery/read/billing callbacks
    if data.get("type") != "message":
        print("⚠️ Not a user message. Ignoring.")
        return "OK", 200


    sender = data["payload"]["sender"]["phone"]
    msg_type = data["payload"]["type"]

    message_text = ""
    button_id = None

    # -------------------------
    # GUPSHUP V2 FORMAT PARSING
    # -------------------------
    try:
        sender = data["payload"]["sender"]["phone"]
        msg_type = data["payload"]["type"]

        if msg_type == "text":
            message_text = data["payload"]["payload"]["text"]

        elif msg_type == "button_reply":
            button_id = data["payload"]["payload"]["postbackText"]
            message_text = data["payload"]["payload"]["title"]

        else:
            message_text = ""

    except Exception as e:
        print("❌ Parsing error:", e)
        return "Parse error", 200

    if not sender:
        print("❌ Sender missing FINAL")
        return "No sender", 200

    sender = clean_number(sender)

    print("✅ FINAL SENDER:", sender)
    print("✅ FINAL MESSAGE:", message_text)
    print("✅ FINAL BUTTON:", button_id)
    # Prevent duplicate button processing
    unique_key = f"{sender}-{button_id or message_text}"

    if last_processed.get(sender) == unique_key:
        print("⚠️ Duplicate event ignored")
        return "OK", 200

    last_processed[sender] = unique_key

    # Process message
    result = process_message(sender, message_text, button_id=button_id)

    # Send response
    if result["type"] == "menu":
        gupshup_send_buttons(sender)
        gupshup_send_buttons_2(sender)
    elif result["type"] == "menu_repeat":
        gupshup_send_buttons_2(sender)

    elif result["type"] == "trial_buttons":
        gupshup_send_trial_buttons(sender, result["name"])

    elif result["type"] == "transformations":
        gupshup_send_text(sender, "🔥 Here are some real transformations from our gym 💪")
        for img_url in TRANSFORMATION_IMAGES:
            gupshup_send_image(sender, img_url)

    elif result["type"] == "gym_images":
        gupshup_send_text(sender, "🏋️ Here are some real photos of our gym 💪🔥")
        for img_url in GYM_IMAGES:
            gupshup_send_image(sender, img_url)


    else:
        gupshup_send_text(sender, result["text"])



    return "OK", 200



# ============================================================
#                       RUN SERVER
# ============================================================



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
