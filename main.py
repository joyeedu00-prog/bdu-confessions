import os
import json
import logging
import telebot
from telebot import types
from threading import Thread
from flask import Flask

# Configure logging
logging.basicConfig(level=logging.INFO)

# --- MINI WEB SERVER (Keeps Render Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "BDU Confessions Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

keep_alive()

# ---------------- CONFIGURATION ----------------
BOT_TOKEN = "8709978309:AAHhNljZGqP9Cb7PuiXrGyNp1ztSj_644SQ"
ADMIN_GROUP_ID = -1004308348205    # Private Admin review group
CHANNEL_ID = "@bduconfession00"    # Public channel
BOT_USERNAME = "bdu_new_confessions_bot"
# ------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

COUNTER_FILE = "confession_count.txt"
COMMENTS_FILE = "confession_comments.json"
POSTS_MAP_FILE = "confession_posts.json"

# --- Persistent Counter ---
def get_counter():
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r") as f:
                return int(f.read().strip())
        except Exception:
            return 1
    return 1

def save_counter(num):
    try:
        with open(COUNTER_FILE, "w") as f:
            f.write(str(num))
    except Exception as e:
        print(f"Error saving counter: {e}")

confession_counter = get_counter()

# --- Persistent Comments ---
def load_comments():
    if os.path.exists(COMMENTS_FILE):
        try:
            with open(COMMENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_comments(data):
    try:
        with open(COMMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving comments: {e}")

comments_db = load_comments()

# --- Persistent Post Mapping (Confession # -> Channel Message ID) ---
def load_posts_map():
    if os.path.exists(POSTS_MAP_FILE):
        try:
            with open(POSTS_MAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_posts_map(data):
    try:
        with open(POSTS_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving posts map: {e}")

posts_map = load_posts_map()

# User session state
users_data = {}

ALL_CATEGORIES = [
    "Relationship", "Family", "Exam", "School",
    "Friendship", "Religion", "Mental", "Addiction",
    "Harassment", "Crush", "Health", "Trauma",
    "Sexual", "Other"
]

# ---------- KEYBOARDS ----------

def persistent_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(types.KeyboardButton("✍️ Confess"))
    markup.row(types.KeyboardButton("👤 Profile"), types.KeyboardButton("ℹ️ Help"))
    return markup

def cancel_reply_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("❌ Cancel"))
    return markup

def preview_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✅ Submit", callback_data="btn_submit"),
        types.InlineKeyboardButton("✍️ Edit", callback_data="btn_edit"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel")
    )
    return markup

def categories_inline_markup(selected_cats):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for cat in ALL_CATEGORIES:
        prefix = "✅ " if cat in selected_cats else ""
        buttons.append(types.InlineKeyboardButton(f"{prefix}{cat}", callback_data=f"toggle_{cat}"))
    markup.add(*buttons)
    count = len(selected_cats)
    markup.row(types.InlineKeyboardButton(f"➡️ Done Selecting ({count}/3)", callback_data="done_cats"))
    markup.row(types.InlineKeyboardButton("❌ Cancel Selection", callback_data="btn_cancel"))
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

def comment_action_markup(c_num, c_idx, likes, dislikes):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.row(
        types.InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{c_num}_{c_idx}"),
        types.InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{c_num}_{c_idx}"),
        types.InlineKeyboardButton("Reply", callback_data=f"rep_{c_num}_{c_idx}")
    )
    return markup

def channel_comment_button(c_num, count):
    markup = types.InlineKeyboardMarkup()
    comment_url = f"https://t.me/{BOT_USERNAME}?start=comm_{c_num}"
    markup.add(types.InlineKeyboardButton(f"💬 View / Add Comments ({count})", url=comment_url))
    return markup

# ---------- REAL-TIME CHANNEL BUTTON UPDATE ----------

def update_channel_comment_count(c_num):
    c_key = str(c_num)
    msg_id = posts_map.get(c_key)
    
    # Reload freshest data from memory/disk
    global comments_db
    total_comments = len(comments_db.get(c_key, []))
    
    if not msg_id:
        print(f"[Warning] No message ID found for confession #{c_num}")
        return

    try:
        bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=int(msg_id),
            reply_markup=channel_comment_button(c_num, total_comments)
        )
        print(f"[Success] Updated Confession #{c_num} button count to {total_comments}")
    except Exception as e:
        print(f"[Error] Failed to edit channel markup: {e}")

# ---------- COMMENT SECTION VIEWER ----------

def display_comment_thread(chat_id, c_num):
    c_key = str(c_num)
    global comments_db
    post_comments = comments_db.get(c_key, [])
    total = len(post_comments)

    if total == 0:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add Comment", callback_data=f"write_comm_{c_num}"))
        bot.send_message(
            chat_id,
            f"💬 *Comments for Confession #{c_num}*\n\nNo comments yet. Be the first to share your thoughts anonymously!",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    for idx, c in enumerate(post_comments):
        text = (
            f"💬 {c['text']}\n\n"
            f"👤 *Anonymous* ⚡️ {c.get('aura', 0)} Aura"
        )
        bot.send_message(
            chat_id,
            text,
            reply_markup=comment_action_markup(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
        )

    footer_markup = types.InlineKeyboardMarkup()
    footer_markup.add(types.InlineKeyboardButton("➕ Add Comment", callback_data=f"write_comm_{c_num}"))
    bot.send_message(
        chat_id,
        f"Displaying {total} Comment(s)",
        reply_markup=footer_markup
    )

# ---------- MESSAGE HANDLERS ----------

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.chat.id
    if uid not in users_data:
        users_data[uid] = {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None}

    parts = message.text.split()
    if len(parts) > 1 and parts[1].startswith("comm_"):
        try:
            c_num = int(parts[1].replace("comm_", ""))
            users_data[uid]["target_confession"] = str(c_num)
            display_comment_thread(uid, c_num)
            return
        except Exception as e:
            print(f"Error handling start comm link: {e}")

    users_data[uid]["state"] = "IDLE"
    welcome_text = "Welcome! Use Confess to submit confessions"
    bot.send_message(uid, welcome_text, reply_markup=persistent_reply_keyboard())

@bot.message_handler(func=lambda m: m.text == "✍️️ Confess")
def handle_confess_button(message):
    uid = message.chat.id
    if uid not in users_data:
        users_data[uid] = {"aura": 0}
    users_data[uid]["state"] = "WAITING_TEXT"
    users_data[uid]["text"] = ""
    users_data[uid]["categories"] = []
    msg = "Please send the text of your confession. You will be able to review, edit, or enhance it next"
    bot.send_message(uid, msg, reply_markup=cancel_reply_keyboard())

@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel_button(message):
    uid = message.chat.id
    if uid in users_data:
        users_data[uid]["state"] = "IDLE"
        users_data[uid]["categories"] = []
        users_data[uid]["text"] = ""
        users_data[uid]["target_confession"] = None
    bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=persistent_reply_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def handle_profile_button(message):
    uid = message.chat.id
    data = users_data.get(uid, {"aura": 0})
    profile_text = (
        "*None Anonymous*\n\n"
        f"⚡️ *Aura:* {data.get('aura', 0)}\n"
        f"👥 *Followers:* 0 | *Following:* 0\n\n"
        "_No bio set_"
    )
    bot.send_message(uid, profile_text, reply_markup=profile_inline_markup(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def handle_help_button(message):
    help_text = (
        "ℹ️ *BDU Confessions Help*\n\n"
        "• Tap *✍️️ Confess* to submit a secret or campus story.\n"
        "• Submissions and comments are 100% anonymous.\n"
        "• Respect community guidelines: No names, no doxxing, no hate speech."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=persistent_reply_keyboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type == 'private')
def handle_text_inputs(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"state": "IDLE", "text": "", "categories": [], "aura": 0, "target_confession": None})

    if user.get("state") == "WAITING_TEXT":
        user["text"] = message.text
        user["state"] = "PREVIEW"
        preview_text = f"Here is a preview of your confession:\n\n_{message.text}_\n\nPlease review it and choose an option below."
        bot.send_message(uid, preview_text, reply_markup=preview_inline_markup(), parse_mode="Markdown")

    elif user.get("state") == "WAITING_COMMENT":
        target = user.get("target_confession")
        if not target:
            bot.send_message(uid, "Session expired. Please click 'View / Add Comments' from the channel again.", reply_markup=persistent_reply_keyboard())
            user["state"] = "IDLE"
            return

        c_key = str(target)
        new_comment = {
            "text": message.text,
            "aura": user.get("aura", 0),
            "likes": 0,
            "dislikes": 0
        }

        global comments_db
        if c_key not in comments_db:
            comments_db[c_key] = []
        
        comments_db[c_key].append(new_comment)
        save_comments(comments_db)

        # Immediately update the channel button live (1, 2, 3...)
        update_channel_comment_count(c_key)

        user["aura"] = user.get("aura", 0) + 2
        user["state"] = "IDLE"

        bot.send_message(uid, "✅ *Your anonymous comment has been posted!*", reply_markup=persistent_reply_keyboard(), parse_mode="Markdown")
        display_comment_thread(uid, c_key)

# ---------- INLINE CALLBACKS ----------

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
        user["categories"] = []
        user["text"] = ""
        user["target_confession"] = None
        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=persistent_reply_keyboard())

    elif data == "btn_submit":
        user["categories"] = []
        user["state"] = "CHOOSING_CATEGORIES"
        bot.edit_message_text(
            "Great! Now, please choose categories for your confession.",
            chat_id=uid, message_id=call.message.message_id,
            reply_markup=categories_inline_markup([])
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
        bot.edit_message_reply_markup(chat_id=uid, message_id=call.message.message_id, reply_markup=categories_inline_markup(current_cats))
        bot.answer_callback_query(call.id, f"'{cat}' updated.")

    elif data == "done_cats":
        selected = user.get("categories", []) or ["other"]
        cat_hashtags = " ".join([f"#{c.lower()}" for c in selected])
        confession_body = user.get("text", "")

        admin_markup = types.InlineKeyboardMarkup(row_width=2)
        admin_markup.add(
            types.InlineKeyboardButton("✅ Approve & Post", callback_data=f"adm_app_{uid}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"adm_rej_{uid}")
        )
        
        admin_card = f"*Pending Confession*\n\n{confession_body}\n\n{cat_hashtags}"
        bot.send_message(ADMIN_GROUP_ID, admin_card, reply_markup=admin_markup, parse_mode="Markdown")

        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass

        bot.send_message(uid, "✅ Your confession has been submitted and is pending review.", reply_markup=persistent_reply_keyboard())
        
        user["aura"] = user.get("aura", 0) + 5
        user["state"] = "IDLE"
        user["categories"] = []
        user["text"] = ""

    elif data.startswith("adm_rej_"):
        bot.edit_message_text("❌ *Submission Rejected.*", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")

    elif data.startswith("adm_app_"):
        global confession_counter, posts_map
        target_uid = data.replace("adm_app_", "")
        raw = call.message.text
        
        parts = raw.split("\n\n")
        if len(parts) >= 3:
            body = "\n\n".join(parts[1:-1])
            hashtags = parts[-1]
        else:
            body = raw
            hashtags = "#other"

        current_num = confession_counter
        channel_post = f"*Confession #{current_num}*\n\n{body}\n\n{hashtags}"

        channel_msg = bot.send_message(
            CHANNEL_ID,
            channel_post,
            reply_markup=channel_comment_button(current_num, 0),
            parse_mode="Markdown"
        )

        # Store channel message ID permanently
        posts_map[str(current_num)] = channel_msg.message_id
        save_posts_map(posts_map)

        try:
            bot.send_message(
                target_uid,
                f"🎉 *Your confession has been approved and published!*\n\nIt is now live as *Confession #{current_num}* on {CHANNEL_ID}.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        bot.edit_message_text(
            f"✅ *Published as Confession #{current_num}*\n\n{body}\n\n{hashtags}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )

        confession_counter += 1
        save_counter(confession_counter)

    elif data.startswith("write_comm_"):
        c_num = data.replace("write_comm_", "")
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        bot.send_message(
            uid,
            f"✍️ Type your anonymous comment for *Confession #{c_num}*:",
            reply_markup=cancel_reply_keyboard(),
            parse_mode="Markdown"
        )

    elif data.startswith("like_") or data.startswith("dislike_"):
        action, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        global comments_db
        if c_num in comments_db and idx < len(comments_db[c_num]):
            if action == "like":
                comments_db[c_num][idx]["likes"] = comments_db[c_num][idx].get("likes", 0) + 1
            else:
                comments_db[c_num][idx]["dislikes"] = comments_db[c_num][idx].get("dislikes", 0) + 1
            save_comments(comments_db)
            
            c = comments_db[c_num][idx]
            bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=call.message.message_id,
                reply_markup=comment_action_markup(c_num, idx, c["likes"], c["dislikes"])
            )
            bot.answer_callback_query(call.id, "Reaction recorded!")

    elif data.startswith("rep_"):
        bot.answer_callback_query(call.id, "Type your comment using '+ Add Comment' button.")

# --- CLEAN STARTUP ---
print("BDU Confession Bot is starting up...")
bot.remove_webhook()
bot.infinity_polling(skip_pending=True)
