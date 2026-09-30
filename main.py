import os
import json
import html
import time
from threading import Thread, Lock
from flask import Flask
import telebot
from telebot import types

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8709978309:AAGvCp4sd7eBBwzhsaCKmXZS-XpoQlRH_-g")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004308348205"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@bduconfession00")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bdu_new_confessions_bot")
# -------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
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

# --- FILE NAMES ---
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
            print(f"[Error] Failed saving comments store: {e}")

users_data = {}
rate_limit_cache = {}

# --- ORIGINAL 14 CATEGORIES RESTORED ---
ALL_CATEGORIES = [
    "Relationship", "Family", "Exam", "School",
    "Friendship", "Religion", "Mental", "Addiction",
    "Harassment", "Crush", "Health", "Trauma",
    "Sexual", "Other"
]

# ---------- KEYBOARDS ----------

def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(types.KeyboardButton("✍️ Confess"))
    markup.row(types.KeyboardButton("👤 Profile"), types.KeyboardButton("ℹ️ Help"))
    return markup

def cancel_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("❌ Cancel"))
    return markup

def confession_preview_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ Submit", callback_data="btn_submit"),
        types.InlineKeyboardButton("✍️ Edit", callback_data="btn_edit")
    )
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel"))
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
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel"))
    return markup

def channel_comment_button(c_num, count):
    markup = types.InlineKeyboardMarkup()
    url = f"https://t.me/{BOT_USERNAME}?start=comm_{c_num}"
    markup.add(types.InlineKeyboardButton(f"💬 View / Add Comments ({count})", url=url))
    return markup

def comment_action_keyboard(c_num, c_idx, likes, dislikes):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.row(
        types.InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{c_num}_{c_idx}"),
        types.InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{c_num}_{c_idx}"),
        types.InlineKeyboardButton("Reply", callback_data=f"rep_{c_num}_{c_idx}")
    )
    return markup

def profile_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(types.InlineKeyboardButton("✍️ Edit Profile", callback_data="prof_edit"))
    markup.row(types.InlineKeyboardButton("📑 My Confessions", callback_data="prof_confessions"),
               types.InlineKeyboardButton("💬 My Comments", callback_data="prof_comments"))
    markup.row(types.InlineKeyboardButton("👥 Following", callback_data="prof_following"),
               types.InlineKeyboardButton("👥 Followers", callback_data="prof_followers"))
    markup.row(types.InlineKeyboardButton("⚙️ Settings", callback_data="prof_settings"))
    markup.row(types.InlineKeyboardButton("💬 My Chats", callback_data="prof_chats"))
    return markup

# ---------- REAL-TIME CHANNEL BUTTON UPDATE ----------

def update_channel_counter(c_num):
    store = load_comments_store()
    c_key = str(c_num)
    meta = store.get(c_key, {})
    
    msg_id = meta.get("channel_msg_id") if isinstance(meta, dict) else None
    
    # Handle both new dictionary format and legacy list format
    if isinstance(meta, dict):
        comments_list = meta.get("comments", [])
    elif isinstance(meta, list):
        comments_list = meta
    else:
        comments_list = []
        
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

# ---------- COMMENT SECTION VIEWER ----------

def render_comment_thread(chat_id, c_num):
    store = load_comments_store()
    c_key = str(c_num)
    post_data = store.get(c_key, {})

    # Support backward compatibility if an entry was saved purely as a list
    if isinstance(post_data, list):
        comments_list = post_data
    elif isinstance(post_data, dict):
        comments_list = post_data.get("comments", [])
    else:
        comments_list = []

    total = len(comments_list)

    if total == 0:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add Comment", callback_data=f"write_comm_{c_num}"))
        bot.send_message(
            chat_id,
            f"💬 <b>Comments for Confession #{c_num}</b>\n\nNo comments yet. Be the first to share your thoughts anonymously!",
            reply_markup=markup
        )
        return

    for idx, c in enumerate(comments_list):
        safe_comm = html.escape(c.get("text", ""))
        safe_date = html.escape(c.get("timestamp", ""))
        date_str = f" • <small>{safe_date}</small>" if safe_date else ""
        text = (
            f"💬 {safe_comm}\n\n"
            f"👤 <b>Anonymous</b> ⚡️ {c.get('aura', 0)} Aura{date_str}"
        )
        bot.send_message(
            chat_id,
            text,
            reply_markup=comment_action_keyboard(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
        )

    bottom_markup = types.InlineKeyboardMarkup()
    bottom_markup.add(types.InlineKeyboardButton("➕ Add Comment", callback_data=f"write_comm_{c_num}"))
    bot.send_message(chat_id, f"Displaying page 1/1. Total {total} Comments", reply_markup=bottom_markup)

# ---------- MESSAGE HANDLERS ----------

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})

    # Robust parsing of deep-linking start argument (e.g. /start comm_12)
    raw_text = message.text or ""
    parts = raw_text.strip().split()

    if len(parts) > 1 and "comm_" in parts[1]:
        try:
            c_num_str = parts[1].split("comm_")[1].strip()
            if c_num_str.isdigit():
                c_num = int(c_num_str)
                user["target_confession"] = str(c_num)
                user["state"] = "IDLE"
                render_comment_thread(uid, c_num)
                return
        except Exception as e:
            print(f"[Error] Deep-link redirection failed: {e}")

    user["state"] = "IDLE"
    welcome_text = "Welcome! Use Confess to submit confessions"
    bot.send_message(uid, welcome_text, reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "✍️ Confess")
def handle_confess_click(message):
    uid = message.chat.id
    now = time.time()
    
    # 20-second cooldown
    if now - rate_limit_cache.get(uid, 0) < 20:
        remaining = int(20 - (now - rate_limit_cache.get(uid, 0)))
        bot.send_message(uid, f"⏳ Please wait {remaining} seconds before submitting another confession.")
        return

    user = users_data.setdefault(uid, {"aura": 0})
    user["state"] = "WAITING_TEXT"
    user["text"] = ""
    user["categories"] = []

    msg = "Please send the text of your confession. You will be able to review, edit, or enhance it next"
    bot.send_message(uid, msg, reply_markup=cancel_reply_keyboard())

@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel_click(message):
    uid = message.chat.id
    if uid in users_data:
        users_data[uid]["state"] = "IDLE"
        users_data[uid]["text"] = ""
        users_data[uid]["categories"] = []
        users_data[uid]["target_confession"] = None
    bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def handle_profile_click(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"aura": 0})
    aura = user.get("aura", 0)

    profile_text = (
        "<b>None Anonymous</b>\n\n"
        f"⚡️ <b>Aura:</b> {aura}\n"
        "👥 <b>Followers:</b> 0 | <b>Following:</b> 0\n\n"
        "<i>No bio set</i>"
    )
    bot.send_message(uid, profile_text, reply_markup=profile_inline_markup())

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def handle_help_click(message):
    help_text = (
        "ℹ️ <b>BDU Confessions Help</b>\n\n"
        "• Tap <b>✍️ Confess</b> to submit a secret or campus story.\n"
        "• Submissions and comments are 100% anonymous.\n"
        "• Respect community guidelines: No names, no doxxing, no hate speech."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.chat.type == 'private')
def handle_text_flow(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})
    raw_text = (message.text or "").strip()

    if user.get("state") == "WAITING_TEXT":
        if len(raw_text) < 10:
            bot.send_message(uid, "⚠️ Your confession is too short. Please provide at least 10 characters.")
            return
        if len(raw_text) > 1500:
            bot.send_message(uid, "⚠️ Your confession exceeds the 1,500 character limit.")
            return

        user["text"] = raw_text
        user["state"] = "PREVIEW"

        preview_body = html.escape(raw_text)
        preview_text = (
            "Here is a preview of your confession:\n\n"
            f"<i>{preview_body}</i>\n\n"
            "Please review it and choose an option below."
        )
        bot.send_message(uid, preview_text, reply_markup=confession_preview_keyboard())

    elif user.get("state") == "WAITING_COMMENT":
        target = user.get("target_confession")
        if not target:
            bot.send_message(uid, "Session expired. Please click '💬 View / Add Comments' from the channel again.", reply_markup=main_menu_keyboard())
            user["state"] = "IDLE"
            return

        if len(raw_text) < 2:
            bot.send_message(uid, "⚠️ Comment cannot be empty.")
            return

        c_key = str(target)
        store = load_comments_store()

        if c_key not in store:
            store[c_key] = {"channel_msg_id": None, "comments": []}
        elif isinstance(store[c_key], list):
            # Convert legacy flat list to dict format
            store[c_key] = {"channel_msg_id": None, "comments": store[c_key]}

        new_entry = {
            "text": raw_text,
            "aura": user.get("aura", 0),
            "likes": 0,
            "dislikes": 0,
            "timestamp": time.strftime("%b %d, %H:%M")
        }

        store[c_key]["comments"].append(new_entry)
        save_comments_store(store)

        # Update the button count immediately on the channel
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
        bot.edit_message_text("Please send the updated text of your confession:", chat_id=uid, message_id=call.message.message_id)

    elif data == "btn_cancel":
        user["state"] = "IDLE"
        user["text"] = ""
        user["categories"] = []
        user["target_confession"] = None
        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard())

    elif data == "btn_submit":
        user["categories"] = []
        user["state"] = "CHOOSING_CATEGORIES"
        bot.edit_message_text(
            "Great! Now, please choose categories for your confession.",
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
                bot.answer_callback_query(call.id, "You can select a maximum of 3 categories.", show_alert=True)
                return
            current_cats.append(cat)
        user["categories"] = current_cats
        bot.edit_message_reply_markup(
            chat_id=uid,
            message_id=call.message.message_id,
            reply_markup=category_selector_keyboard(current_cats)
        )
        bot.answer_callback_query(call.id, f"'{cat}' updated.")

    elif data == "done_cats":
        selected = user.get("categories", []) or ["Other"]
        cat_hashtags = " ".join([f"#{c.lower()}" for c in selected])
        confession_body = user.get("text", "")

        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Approve & Post", callback_data=f"adm_app_{uid}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{uid}")
        )

        safe_body = html.escape(confession_body)
        admin_card = f"<b>Pending Confession</b>\n\n{safe_body}\n\n{cat_hashtags}"
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

        bot.send_message(uid, "✅ Your confession has been submitted and is pending review.", reply_markup=main_menu_keyboard())

    elif data.startswith("adm_rej_"):
        bot.edit_message_text("❌ <b>Submission Rejected.</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("adm_app_"):
        target_uid = data.replace("adm_app_", "")
        current_num = get_current_counter()

        raw = call.message.text or ""
        parts = raw.split("\n\n")
        if len(parts) >= 3:
            body = "\n\n".join(parts[1:-1])
            hashtags = parts[-1]
        else:
            body = raw
            hashtags = "#other"

        safe_body = html.escape(body)
        channel_post = f"<b>Confession #{current_num}</b>\n\n{safe_body}\n\n{hashtags}"

        channel_msg = bot.send_message(
            CHANNEL_ID,
            channel_post,
            reply_markup=channel_comment_button(current_num, 0)
        )

        # Store channel message ID inside confession_comments.json
        store = load_comments_store()
        c_key = str(current_num)
        if c_key not in store or isinstance(store[c_key], list):
            existing_comms = store[c_key] if isinstance(store.get(c_key), list) else []
            store[c_key] = {"channel_msg_id": channel_msg.message_id, "comments": existing_comms}
        else:
            store[c_key]["channel_msg_id"] = channel_msg.message_id
        save_comments_store(store)

        # Increment persistent counter
        save_counter(current_num + 1)

        try:
            bot.send_message(
                int(target_uid),
                f"🎉 <b>Your confession has been approved and published!</b>\n\nIt is now live as <b>Confession #{current_num}</b> on {CHANNEL_ID}."
            )
        except Exception:
            pass

        bot.edit_message_text(
            f"✅ <b>Published as Confession #{current_num}</b>\n\n{safe_body}\n\n{hashtags}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    elif data.startswith("write_comm_"):
        c_num = data.replace("write_comm_", "")
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        bot.send_message(
            uid,
            f"✍️ Type your anonymous comment for <b>Confession #{c_num}</b>:",
            reply_markup=cancel_reply_keyboard()
        )

    elif data.startswith("like_") or data.startswith("dislike_"):
        action, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        store = load_comments_store()
        c_key = str(c_num)

        meta = store.get(c_key, {})
        comments_list = meta.get("comments", []) if isinstance(meta, dict) else meta if isinstance(meta, list) else []

        if idx < len(comments_list):
            target_c = comments_list[idx]
            if action == "like":
                target_c["likes"] = target_c.get("likes", 0) + 1
            else:
                target_c["dislikes"] = target_c.get("dislikes", 0) + 1
            save_comments_store(store)

            bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=call.message.message_id,
                reply_markup=comment_action_keyboard(c_num, idx, target_c.get("likes", 0), target_c.get("dislikes", 0))
            )
            bot.answer_callback_query(call.id, "Reaction recorded!")

    elif data.startswith("rep_"):
        bot.answer_callback_query(call.id, "Use '+ Add Comment' to post your reply.")

# --- CLEAN STARTUP & RECOVERY ---
print("BDU Confession Bot Engine starting...")
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook clearance notice: {e}")

bot.infinity_polling(skip_pending=True)
