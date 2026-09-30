import os
import json
import html
import time
from threading import Thread, Lock
from flask import Flask
import telebot
from telebot import types

# ----------------- CONFIGURATION -----------------
# Tip: You can also set BOT_TOKEN as an environment variable in Render!
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8709978309:AAGvCp4sd7eBBwzhsaCKmXZS-XpoQlRH_-g")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004308348205"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@bduconfession00")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bdu_new_confessions_bot")
# -------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Thread lock to avoid JSON corruption during concurrent writes
db_lock = Lock()

# --- MINI WEB SERVER (Keeps Render Free Tier Awake) ---
web_app = Flask('')

@web_app.route('/')
def health_check():
    return "BDU Confessions Engine 24/7 is Live & Healthy!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

def keep_alive():
    server_thread = Thread(target=run_web)
    server_thread.daemon = True
    server_thread.start()

keep_alive()

# --- FILE NAMES MATCHING REPOSITORY ---
COUNTER_FILE = "confession_count.txt"
COMMENTS_FILE = "confession_comments.json"

# --- PERSISTENCE LOGIC ---
def get_current_counter():
    with db_lock:
        if os.path.exists(COUNTER_FILE):
            try:
                with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                    return int(f.read().strip())
            except Exception:
                return 1
        return 1

def save_counter(num):
    with db_lock:
        try:
            with open(COUNTER_FILE, "w", encoding="utf-8") as f:
                f.write(str(num))
        except Exception as e:
            print(f"[Error] Failed saving counter: {e}")

def load_comments_store():
    with db_lock:
        if os.path.exists(COMMENTS_FILE):
            try:
                with open(COMMENTS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def save_comments_store(data):
    with db_lock:
        try:
            with open(COMMENTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Error] Failed saving comments database: {e}")

# In-memory session tracking and anti-spam
users_data = {}
rate_limit_cache = {}

ALL_CATEGORIES = [
    "Relationship", "Campus Life", "Exams", "Friendship",
    "Crush", "Mental Health", "Advice", "Lost & Found",
    "Staff/Professors", "Hostel/Dorm", "Funny", "Other"
]

# ---------- KEYBOARDS ----------

def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(types.KeyboardButton("✍️ Send Confession"))
    markup.row(types.KeyboardButton("👤 My Profile"), types.KeyboardButton("ℹ️ Guidelines & Rules"))
    return markup

def cancel_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("❌ Cancel"))
    return markup

def confession_preview_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ Submit for Review", callback_data="btn_submit"),
        types.InlineKeyboardButton("✍️ Edit Text", callback_data="btn_edit")
    )
    markup.row(types.InlineKeyboardButton("❌ Discard", callback_data="btn_cancel"))
    return markup

def category_selector_keyboard(selected_cats):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cat in ALL_CATEGORIES:
        status_icon = "✅ " if cat in selected_cats else ""
        buttons.append(types.InlineKeyboardButton(f"{status_icon}{cat}", callback_data=f"toggle_{cat}"))
    markup.add(*buttons)
    count = len(selected_cats)
    markup.row(types.InlineKeyboardButton(f"➡️ Done Selecting ({count}/3)", callback_data="done_cats"))
    markup.row(types.InlineKeyboardButton("❌ Cancel Submission", callback_data="btn_cancel"))
    return markup

def channel_comment_button(c_num, count):
    markup = types.InlineKeyboardMarkup()
    url = f"https://t.me/{BOT_USERNAME}?start=comm_{c_num}"
    markup.add(types.InlineKeyboardButton(f"💬 View / Add Comments ({count})", url=url))
    return markup

def comment_action_keyboard(c_num, c_idx, likes, dislikes):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{c_num}_{c_idx}"),
        types.InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{c_num}_{c_idx}")
    )
    return markup

# ---------- HELPER: REAL-TIME CHANNEL BUTTON UPDATE ----------

def update_channel_counter(c_num):
    store = load_comments_store()
    c_key = str(c_num)
    meta = store.get(c_key, {})
    
    # Check if channel_msg_id is preserved
    msg_id = meta.get("channel_msg_id")
    comments_list = meta.get("comments", [])
    count = len(comments_list)

    if not msg_id:
        print(f"[Notice] No channel message ID mapped for Confession #{c_num}.")
        return

    try:
        bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=int(msg_id),
            reply_markup=channel_comment_button(c_num, count)
        )
        print(f"[Success] Updated Confession #{c_num} live button counter to: ({count})")
    except Exception as e:
        print(f"[Warning] Could not update channel message markup: {e}")

# ---------- COMMENT VIEWER ----------

def render_comment_thread(chat_id, c_num):
    store = load_comments_store()
    c_key = str(c_num)
    post_data = store.get(c_key, {})
    comments_list = post_data.get("comments", [])
    total = len(comments_list)

    if total == 0:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add the First Comment", callback_data=f"write_comm_{c_num}"))
        bot.send_message(
            chat_id,
            f"💬 <b>Comments for Confession #{c_num}</b>\n\nNo comments yet! Be the first to share your thoughts anonymously.",
            reply_markup=markup
        )
        return

    bot.send_message(chat_id, f"💬 <b>Discussion for Confession #{c_num}</b> ({total} comments):")

    for idx, c in enumerate(comments_list):
        safe_comm = html.escape(c.get("text", ""))
        safe_date = html.escape(c.get("timestamp", ""))
        text = (
            f"🗣️ <i>\"{safe_comm}\"</i>\n\n"
            f"👤 <b>Anonymous Student</b> • ⚡️ {c.get('aura', 0)} Aura\n"
            f"🕒 <small>{safe_date}</small>"
        )
        bot.send_message(
            chat_id,
            text,
            reply_markup=comment_action_keyboard(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
        )

    bottom_markup = types.InlineKeyboardMarkup()
    bottom_markup.add(types.InlineKeyboardButton("➕ Add Your Comment", callback_data=f"write_comm_{c_num}"))
    bot.send_message(chat_id, f"End of comments. Total: {total}", reply_markup=bottom_markup)

# ---------- MESSAGE HANDLERS ----------

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})

    text_parts = message.text.split()
    if len(text_parts) > 1 and text_parts[1].startswith("comm_"):
        try:
            c_num = int(text_parts[1].replace("comm_", ""))
            user["target_confession"] = str(c_num)
            render_comment_thread(uid, c_num)
            return
        except Exception:
            pass

    user["state"] = "IDLE"
    welcome_msg = (
        "👋 <b>Welcome to BDU Anonymous Confessions!</b>\n\n"
        "Share campus secrets, ask questions, or vent anonymously.\n"
        "• Your identity is 100% private.\n"
        "• Submissions are reviewed by moderators before posting.\n\n"
        "Tap <b>✍️ Send Confession</b> below to get started!"
    )
    bot.send_message(uid, welcome_msg, reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "✍️ Send Confession" or m.text == "✍️ Confess")
def handle_confess_click(message):
    uid = message.chat.id
    now = time.time()
    
    # 30-second rate limiter to stop spam
    if now - rate_limit_cache.get(uid, 0) < 30:
        remaining = int(30 - (now - rate_limit_cache.get(uid, 0)))
        bot.send_message(uid, f"⏳ Please wait {remaining} seconds before submitting another confession.")
        return

    user = users_data.setdefault(uid, {"aura": 0})
    user["state"] = "WAITING_TEXT"
    user["text"] = ""
    user["categories"] = []

    guide = (
        "✍️ <b>Write your confession below and send it.</b>\n\n"
        "<i>Rules:</i>\n"
        "• Length: 15 to 1,000 characters.\n"
        "• Do not mention full personal names, phone numbers, or hate speech.\n"
        "• You will get a preview to confirm before sending."
    )
    bot.send_message(uid, guide, reply_markup=cancel_reply_keyboard())

@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel_click(message):
    uid = message.chat.id
    if uid in users_data:
        users_data[uid]["state"] = "IDLE"
        users_data[uid]["text"] = ""
        users_data[uid]["categories"] = []
        users_data[uid]["target_confession"] = None
    bot.send_message(uid, "❌ Operation cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 My Profile" or m.text == "👤 Profile")
def handle_profile_click(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"aura": 0})
    aura = user.get("aura", 0)

    rank = "Campus Rookie"
    if aura >= 20: rank = "Active Contributor"
    if aura >= 50: rank = "BDU Legend"

    profile_text = (
        "👤 <b>Anonymous Identity Profile</b>\n\n"
        f"⚡️ <b>Aura Points:</b> {aura}\n"
        f"🏅 <b>Campus Rank:</b> {rank}\n"
        f"🔒 <b>Identity Status:</b> 100% Encrypted & Anonymous\n\n"
        "<i>Earn +5 Aura for approved confessions and +2 Aura for each constructive comment!</i>"
    )
    bot.send_message(uid, profile_text)

@bot.message_handler(func=lambda m: m.text == "ℹ️ Guidelines & Rules" or m.text == "ℹ️ Help")
def handle_help_click(message):
    help_text = (
        "ℹ️ <b>BDU Confessions Community Guidelines</b>\n\n"
        "1. <b>Absolute Anonymity:</b> Nobody (not even admins) can see who submitted a confession.\n"
        "2. <b>Zero Doxxing:</b> Confessions exposing private phone numbers, usernames, or targeted harassment will be rejected.\n"
        "3. <b>Interactive Discussions:</b> Tap the comment button beneath any post on the channel to join the anonymous debate.\n\n"
        "Have fun and keep the campus spirit alive!"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(func=lambda m: m.chat.type == 'private')
def handle_text_flow(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})
    raw_text = message.text.strip()

    if user.get("state") == "WAITING_TEXT":
        # Input validation
        if len(raw_text) < 15:
            bot.send_message(uid, "⚠️ Your confession is too short. Please provide at least 15 characters.")
            return
        if len(raw_text) > 1200:
            bot.send_message(uid, "⚠️ Your confession exceeds the 1,200 character limit. Please shorten it.")
            return

        user["text"] = raw_text
        user["state"] = "PREVIEW"

        preview_body = html.escape(raw_text)
        preview_text = (
            "🔍 <b>Preview Your Confession:</b>\n\n"
            f"<i>\"{preview_body}\"</i>\n\n"
            "Would you like to submit this or edit it?"
        )
        bot.send_message(uid, preview_text, reply_markup=confession_preview_keyboard())

    elif user.get("state") == "WAITING_COMMENT":
        target = user.get("target_confession")
        if not target:
            bot.send_message(uid, "Session timed out. Please tap 'View / Add Comments' under the channel post again.", reply_markup=main_menu_keyboard())
            user["state"] = "IDLE"
            return

        if len(raw_text) < 2:
            bot.send_message(uid, "⚠️ Comment cannot be empty.")
            return
        if len(raw_text) > 500:
            bot.send_message(uid, "⚠️ Comment is too long (maximum 500 characters).")
            return

        c_key = str(target)
        store = load_comments_store()

        if c_key not in store:
            store[c_key] = {"channel_msg_id": None, "comments": []}

        new_entry = {
            "text": raw_text,
            "aura": user.get("aura", 0),
            "likes": 0,
            "dislikes": 0,
            "timestamp": time.strftime("%b %d, %H:%M")
        }

        store[c_key]["comments"].append(new_entry)
        save_comments_store(store)

        # Real-time live counter update on the channel
        update_channel_counter(c_key)

        user["aura"] = user.get("aura", 0) + 2
        user["state"] = "IDLE"

        bot.send_message(uid, "✅ <b>Your anonymous comment has been posted!</b>", reply_markup=main_menu_keyboard())
        render_comment_thread(uid, c_key)

# ---------- INLINE BUTTON HANDLERS ----------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.message.chat.id
    data = call.data
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})

    if data == "btn_edit":
        user["state"] = "WAITING_TEXT"
        bot.edit_message_text("✍️ Send the updated text of your confession:", chat_id=uid, message_id=call.message.message_id)

    elif data == "btn_cancel":
        user["state"] = "IDLE"
        user["text"] = ""
        user["categories"] = []
        user["target_confession"] = None
        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(uid, "❌ Submission cancelled.", reply_markup=main_menu_keyboard())

    elif data == "btn_submit":
        user["categories"] = []
        user["state"] = "CHOOSING_CATEGORIES"
        bot.edit_message_text(
            "🏷️ <b>Select up to 3 tags for your confession:</b>",
            chat_id=uid,
            message_id=call.message.message_id,
            reply_markup=category_selector_keyboard([])
        )

    elif data.startswith("toggle_"):
        cat = data.replace("toggle_", "")
        current_cats = user.get("categories", [])
        if cat in current_cats:
            current_cats.remove(cat)
        else:
            if len(current_cats) >= 3:
                bot.answer_callback_query(call.id, "You can select a maximum of 3 tags.", show_alert=True)
                return
            current_cats.append(cat)
        user["categories"] = current_cats
        bot.edit_message_reply_markup(
            chat_id=uid,
            message_id=call.message.message_id,
            reply_markup=category_selector_keyboard(current_cats)
        )
        bot.answer_callback_query(call.id, f"Tag updated.")

    elif data == "done_cats":
        selected = user.get("categories", []) or ["Other"]
        tags_str = " ".join([f"#{c.replace(' ', '').replace('/', '')}" for c in selected])
        confession_body = user.get("text", "")

        # Format admin moderation card
        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Approve & Publish", callback_data=f"adm_app_{uid}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{uid}")
        )

        safe_body = html.escape(confession_body)
        admin_card = (
            f"📬 <b>New Confession Submitted</b>\n\n"
            f"<blockquote>{safe_body}</blockquote>\n\n"
            f"🏷️ <b>Tags:</b> {tags_str}"
        )
        bot.send_message(ADMIN_GROUP_ID, admin_card, reply_markup=admin_markup)

        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass

        rate_limit_cache[uid] = time.time()
        user["aura"] = user.get("aura", 0) + 5
        user["state"] = "IDLE"
        user["text"] = ""
        user["categories"] = []

        bot.send_message(uid, "✅ <b>Submitted!</b> Your confession is in the admin review queue.", reply_markup=main_menu_keyboard())

    elif data.startswith("adm_rej_"):
        target_uid = data.replace("adm_rej_", "")
        bot.edit_message_text("❌ <b>Submission Rejected by Admin.</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(int(target_uid), "ℹ️ Your confession did not meet community guidelines and was not approved.")
        except Exception:
            pass

    elif data.startswith("adm_app_"):
        target_uid = data.replace("adm_app_", "")
        current_num = get_current_counter()

        # Parse confession text and tags from message
        raw = call.message.text or ""
        tags = "#BDU #Campus"
        body = raw
        if "Tags:" in raw:
            parts = raw.split("Tags:")
            body = parts[0].replace("New Confession Submitted", "").strip()
            tags = parts[1].strip()

        safe_body = html.escape(body)
        channel_post = (
            f"<b>Confession #{current_num}</b>\n\n"
            f"{safe_body}\n\n"
            f"{tags}"
        )

        # Post to public channel with live comment button
        channel_msg = bot.send_message(
            CHANNEL_ID,
            channel_post,
            reply_markup=channel_comment_button(current_num, 0)
        )

        # Map Confession # -> Channel Message ID inside confession_comments.json
        store = load_comments_store()
        c_key = str(current_num)
        if c_key not in store:
            store[c_key] = {"channel_msg_id": channel_msg.message_id, "comments": []}
        else:
            store[c_key]["channel_msg_id"] = channel_msg.message_id
        save_comments_store(store)

        # Increment persistent counter
        save_counter(current_num + 1)

        try:
            bot.send_message(
                int(target_uid),
                f"🎉 <b>Congratulations!</b> Your confession was approved and posted as <b>Confession #{current_num}</b> on {CHANNEL_ID}!"
            )
        except Exception:
            pass

        bot.edit_message_text(
            f"✅ <b>Approved and Posted as #{current_num}</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    elif data.startswith("write_comm_"):
        c_num = data.replace("write_comm_", "")
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        bot.send_message(
            uid,
            f"✍️ Type your anonymous comment for <b>Confession #{c_num}</b>:\n(Max 500 characters)",
            reply_markup=cancel_reply_keyboard()
        )

    elif data.startswith("like_") or data.startswith("dislike_"):
        action, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        store = load_comments_store()
        c_key = str(c_num)

        if c_key in store and idx < len(store[c_key].get("comments", [])):
            target_c = store[c_key]["comments"][idx]
            if action == "like":
                target_c["likes"] = target_c.get("likes", 0) + 1
            else:
                target_c["dislikes"] = target_c.get("dislikes", 0) + 1
            save_comments_store(store)

            bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=call.message.message_id,
                reply_markup=comment_action_keyboard(c_num, idx, target_c["likes"], target_c["dislikes"])
            )
            bot.answer_callback_query(call.id, "Reaction recorded!")

# --- SAFE STARTUP & RECOVERY ---
print("BDU Confession Bot Engine starting...")
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook clearance notice: {e}")

bot.infinity_polling(skip_pending=True)
