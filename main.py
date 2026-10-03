import os
import json
import html
import time
from threading import Thread, Lock
from flask import Flask
import telebot
from telebot import types

# ---------------- CONFIGURATION ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8709978309:AAFQj1-8lauK_j8SNtOUxrL6GGzHVAbaWSI")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004308348205"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@bduconfession00")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bdu_new_confessions_bot")
# ------------------------------------------------

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db_lock = Lock()

# --- MINI WEB SERVER (Keeps Render Free Tier 24/7) ---
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

# --- REPOSITORY STORAGE FILES ---
COUNTER_FILE = "confession_count.txt"
COMMENTS_FILE = "confession_comments.json"
POSTS_MAP_FILE = "confession_posts.json"
USERS_FILE = "confession_users.json"

# --- PERSISTENCE HELPERS ---
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

def load_posts_map():
    with db_lock:
        if os.path.exists(POSTS_MAP_FILE):
            try:
                with open(POSTS_MAP_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def save_posts_map(data):
    with db_lock:
        try:
            with open(POSTS_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Error] Failed saving posts map: {e}")

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

def load_users_store():
    with db_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def save_users_store(data):
    with db_lock:
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Error] Failed saving users store: {e}")

def get_user_profile(uid):
    users = load_users_store()
    s_uid = str(uid)
    if s_uid not in users:
        users[s_uid] = {
            "nickname": None,
            "bio": "No bio set",
            "aura": 0
        }
        save_users_store(users)
    return users[s_uid]

def update_user_profile(uid, nickname=None, bio=None, aura_delta=0):
    users = load_users_store()
    s_uid = str(uid)
    if s_uid not in users:
        users[s_uid] = {
            "nickname": None,
            "bio": "No bio set",
            "aura": 0
        }
    if nickname is not None:
        users[s_uid]["nickname"] = nickname
    if bio is not None:
        users[s_uid]["bio"] = bio
    if aura_delta != 0:
        users[s_uid]["aura"] = max(0, users[s_uid].get("aura", 0) + aura_delta)
    save_users_store(users)
    return users[s_uid]

confession_counter = get_current_counter()
posts_map = load_posts_map()
comments_db = load_comments_store()

users_data = {}
rate_limit_cache = {}

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

def preview_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("✅ Submit", callback_data="btn_submit"),
        types.InlineKeyboardButton("✍ Edit", callback_data="btn_edit")
    )
    markup.row(types.InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel"))
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
    markup.row(types.InlineKeyboardButton("✍ Edit Profile", callback_data="prof_edit"))
    markup.row(types.InlineKeyboardButton("📑 My Confessions", callback_data="prof_confessions"),
               types.InlineKeyboardButton("💬 My Comments", callback_data="prof_comments"))
    markup.row(types.InlineKeyboardButton("👥 Following", callback_data="prof_following"),
               types.InlineKeyboardButton("👥 Followers", callback_data="prof_followers"))
    markup.row(types.InlineKeyboardButton("⚙️ Settings", callback_data="prof_settings"))
    markup.row(types.InlineKeyboardButton("💬 My Chats", callback_data="prof_chats"))
    return markup

def edit_profile_inline_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("✏️ Change Nickname", callback_data="edit_prof_nick"),
        types.InlineKeyboardButton("📝 Set/Update Bio", callback_data="edit_prof_bio"),
        types.InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")
    )
    return markup

def channel_comment_button(c_num, count):
    markup = types.InlineKeyboardMarkup()
    url = f"https://t.me/{BOT_USERNAME}?start=comm_{c_num}"
    markup.add(types.InlineKeyboardButton(f"💬 View / Add Comments ({count})", url=url))
    return markup

def confession_hub_markup(c_num, count):
    markup = types.InlineKeyboardMarkup(row_width=1)
    b_add = types.InlineKeyboardButton("➕ Add Comment", callback_data=f"hub_add_{c_num}")
    b_browse = types.InlineKeyboardButton(f"💬 Browse Comments ({count})", callback_data=f"hub_browse_{c_num}")
    markup.add(b_add, b_browse)
    return markup

def comment_action_markup(c_num, c_idx, likes, dislikes):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.row(
        types.InlineKeyboardButton(f"👍🏼 {likes}", callback_data=f"like_{c_num}_{c_idx}"),
        types.InlineKeyboardButton(f"👎🏼 {dislikes}", callback_data=f"dislike_{c_num}_{c_idx}"),
        types.InlineKeyboardButton("Reply", callback_data=f"rep_{c_num}_{c_idx}")
    )
    return markup

# ---------- BACKUP COMMAND (SENDS FILES IN TELEGRAM) ----------

@bot.message_handler(commands=['backup'])
def handle_backup(message):
    uid = message.chat.id
    # Only allowed from admin group or if initiated by the admin
    if message.chat.id != ADMIN_GROUP_ID and message.from_user.id != ADMIN_GROUP_ID:
        # Check permissions
        try:
            member = bot.get_chat_member(ADMIN_GROUP_ID, message.from_user.id)
            if member.status not in ["creator", "administrator"]:
                bot.send_message(uid, "⚠️ Only admins can use the backup command.")
                return
        except Exception:
            bot.send_message(uid, "⚠️ Only admins can use the backup command.")
            return

    bot.send_message(uid, "📦 <b>Preparing data backup files...</b>", parse_mode="HTML")
    for filename in [COMMENTS_FILE, POSTS_MAP_FILE, COUNTER_FILE, USERS_FILE]:
        if os.path.exists(filename):
            try:
                with open(filename, 'rb') as f:
                    bot.send_document(uid, f, caption=f"📄 {filename}")
            except Exception as e:
                bot.send_message(uid, f"⚠️ Failed sending {filename}: {e}")
        else:
            bot.send_message(uid, f"ℹ️ {filename} does not exist on disk yet.")

# ---------- REAL-TIME CHANNEL BUTTON UPDATE ----------

def update_channel_comment_count(c_num):
    c_key = str(c_num)
    posts = load_posts_map()
    post_info = posts.get(c_key)

    msg_id = None
    if isinstance(post_info, dict):
        msg_id = post_info.get("msg_id")
    elif isinstance(post_info, int):
        msg_id = post_info

    comments_store = load_comments_store()
    raw_entry = comments_store.get(c_key, [])
    if isinstance(raw_entry, dict):
        comments_list = raw_entry.get("comments", [])
    elif isinstance(raw_entry, list):
        comments_list = raw_entry
    else:
        comments_list = []

    total_comments = len(comments_list)

    if not msg_id:
        print(f"[Warning] No message ID found for confession #{c_num}")
        return

    try:
        bot.edit_message_reply_markup(
            chat_id=CHANNEL_ID,
            message_id=int(msg_id),
            reply_markup=channel_comment_button(c_num, total_comments)
        )
        print(f"[Success] Updated Confession #{c_num} button count to ({total_comments})")
    except Exception as e:
        print(f"[Error] Failed to edit channel markup: {e}")

# ---------- CONFESSION LANDING HUB & COMMENT BROWSING ----------

def show_confession_hub(chat_id, c_num):
    c_key = str(c_num)
    posts = load_posts_map()
    post_info = posts.get(c_key, {})

    original_text = ""
    original_tags = ""
    if isinstance(post_info, dict):
        original_text = post_info.get("text", "")
        original_tags = post_info.get("tags", "")

    comments_store = load_comments_store()
    raw_entry = comments_store.get(c_key, [])
    if isinstance(raw_entry, dict):
        comments_list = raw_entry.get("comments", [])
    elif isinstance(raw_entry, list):
        comments_list = raw_entry
    else:
        comments_list = []

    count = len(comments_list)

    if original_text:
        body_display = f"{html.escape(original_text)}\n\n{html.escape(original_tags)}"
    else:
        body_display = "Confession details"

    hub_text = (
        f"📖 <b>Confession #{c_num}</b>\n\n"
        f"{body_display}"
    )
    bot.send_message(chat_id, hub_text, reply_markup=confession_hub_markup(c_num, count), parse_mode="HTML")

def display_browse_comments(chat_id, c_num):
    c_key = str(c_num)
    comments_store = load_comments_store()
    raw_entry = comments_store.get(c_key, [])

    if isinstance(raw_entry, dict):
        comments_list = raw_entry.get("comments", [])
    elif isinstance(raw_entry, list):
        comments_list = raw_entry
    else:
        comments_list = []

    total = len(comments_list)

    if total == 0:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add the First Comment", callback_data=f"hub_add_{c_num}"))
        bot.send_message(
            chat_id,
            f"💬 <b>Comments for Confession #{c_num}</b>\n\nNo comments yet! Be the first to share your thoughts anonymously.",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return

    # Render each comment
    for idx, c in enumerate(comments_list):
        if isinstance(c, str):
            c_text = c
            c_type = "text"
            c_sender_id = None
            c_likes = 0
            c_dislikes = 0
            c_reply_to = None
            c_file_id = None
        elif isinstance(c, dict):
            c_text = c.get("text", "")
            c_type = c.get("type", "text")
            c_sender_id = c.get("sender_id")
            c_likes = len(c.get("liked_by", [])) if isinstance(c.get("liked_by"), list) else c.get("likes", 0)
            c_dislikes = len(c.get("disliked_by", [])) if isinstance(c.get("disliked_by"), list) else c.get("dislikes", 0)
            c_reply_to = c.get("reply_to")
            c_file_id = c.get("file_id")
        else:
            continue

        display_name = "Anonymous"
        aura_count = 0
        link_url = ""
        if c_sender_id:
            author_prof = get_user_profile(c_sender_id)
            if author_prof.get("nickname"):
                display_name = author_prof["nickname"]
            aura_count = author_prof.get("aura", 0)
            link_url = f"https://t.me/{BOT_USERNAME}?start=user_{c_sender_id}"

        safe_name = html.escape(str(display_name))
        if link_url:
            user_link = f"<a href=\"{link_url}\"><b>{safe_name}</b></a>"
        else:
            user_link = f"<b>{safe_name}</b>"

        user_info = f"👤 {user_link}    🔥 {aura_count} Aura"

        # Unique Telegram quote rendering for replied messages
        reply_quote = ""
        if c_reply_to is not None and isinstance(c_reply_to, int) and c_reply_to < len(comments_list):
            ref_c = comments_list[c_reply_to]
            if isinstance(ref_c, str):
                ref_snippet = ref_c
            elif isinstance(ref_c, dict):
                ref_snippet = ref_c.get("text", "Media")
            else:
                ref_snippet = "Comment"
            clean_snippet = html.escape(str(ref_snippet)[:100])
            reply_quote = f"<blockquote>💬 {clean_snippet}</blockquote>\n"

        try:
            if c_type == "sticker" and c_file_id:
                if reply_quote:
                    bot.send_message(chat_id, reply_quote, parse_mode="HTML")
                bot.send_sticker(chat_id, c_file_id)
                bot.send_message(
                    chat_id,
                    user_info,
                    reply_markup=comment_action_markup(c_num, idx, c_likes, c_dislikes),
                    parse_mode="HTML"
                )
            elif c_type == "animation" and c_file_id:
                if reply_quote:
                    bot.send_message(chat_id, reply_quote, parse_mode="HTML")
                bot.send_animation(chat_id, c_file_id)
                bot.send_message(
                    chat_id,
                    user_info,
                    reply_markup=comment_action_markup(c_num, idx, c_likes, c_dislikes),
                    parse_mode="HTML"
                )
            else:
                clean_text = html.escape(str(c_text)) if c_text else ""
                body_message = (
                    f"{reply_quote}"
                    f"💬 {clean_text}\n\n"
                    f"{user_info}"
                )
                bot.send_message(
                    chat_id,
                    body_message,
                    reply_markup=comment_action_markup(c_num, idx, c_likes, c_dislikes),
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"[Error rendering comment]: {e}")
            try:
                fallback_msg = f"{reply_quote}💬 {c_text}\n\n{user_info}"
                bot.send_message(
                    chat_id,
                    fallback_msg,
                    reply_markup=comment_action_markup(c_num, idx, c_likes, c_dislikes),
                    parse_mode="HTML"
                )
            except Exception as e2:
                print(f"[Fatal fallback error]: {e2}")

    bottom_markup = types.InlineKeyboardMarkup()
    bottom_markup.add(types.InlineKeyboardButton("➕ Add Your Comment", callback_data=f"hub_add_{c_num}"))
    bot.send_message(chat_id, f"Displaying {total} comment(s).", reply_markup=bottom_markup, parse_mode="HTML")

# ---------- START COMMAND & DEEP LINKING ----------

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "target_confession": None, "reply_to_idx": None
    })

    raw_text = message.text or ""
    parts = raw_text.strip().split()

    # 1. Deep link: /start comm_X (Confession Hub)
    if len(parts) > 1 and "comm_" in parts[1]:
        try:
            c_num_str = parts[1].split("comm_")[1].strip()
            if c_num_str.isdigit():
                c_num = int(c_num_str)
                user["target_confession"] = str(c_num)
                user["state"] = "IDLE"
                user["reply_to_idx"] = None
                show_confession_hub(uid, c_num)
                return
        except Exception as e:
            print(f"[Error] Deep-link confession redirection error: {e}")

    # 2. Deep link: /start user_USERID (View Public Profile)
    if len(parts) > 1 and "user_" in parts[1]:
        try:
            target_uid = parts[1].split("user_")[1].strip()
            target_profile = get_user_profile(target_uid)

            name = target_profile.get("nickname") or "Anonymous"
            bio = target_profile.get("bio") or "No bio set"
            aura = target_profile.get("aura", 0)

            public_profile_text = (
                f"👤 <b>{html.escape(name)}</b>\n\n"
                f"🔥 <b>Aura:</b> {aura}\n\n"
                f"<i>{html.escape(bio)}</i>"
            )
            bot.send_message(uid, public_profile_text, parse_mode="HTML")
            return
        except Exception as e:
            print(f"[Error] Deep-link profile redirection error: {e}")

    user["state"] = "IDLE"
    welcome_text = "Welcome! Use Confess to submit confessions"
    bot.send_message(uid, welcome_text, reply_markup=main_menu_keyboard(), parse_mode="HTML")

# ---------- MAIN MENU BUTTONS ----------

@bot.message_handler(func=lambda m: m.text == "✍ Confess")
def handle_confess_button(message):
    uid = message.chat.id
    now = time.time()

    if now - rate_limit_cache.get(uid, 0) < 20:
        remaining = int(20 - (now - rate_limit_cache.get(uid, 0)))
        bot.send_message(uid, f"⏳ Please wait {remaining} seconds before submitting another confession.", parse_mode="HTML")
        return

    user = users_data.setdefault(uid, {})
    user["state"] = "WAITING_TEXT"
    user["text"] = ""
    user["categories"] = []
    user["reply_to_idx"] = None
    msg = "Please send the text of your confession. You will be able to review, edit, or enhance it next"
    bot.send_message(uid, msg, reply_markup=cancel_reply_keyboard(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
def handle_cancel_button(message):
    uid = message.chat.id
    if uid in users_data:
        users_data[uid]["state"] = "IDLE"
        users_data[uid]["categories"] = []
        users_data[uid]["text"] = ""
        users_data[uid]["target_confession"] = None
        users_data[uid]["reply_to_idx"] = None
    bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard(), parse_mode="HTML")

def show_my_profile(uid, chat_id=None, message_id=None):
    if not chat_id:
        chat_id = uid
    prof = get_user_profile(uid)
    name = prof.get("nickname") or "None Anonymous"
    bio = prof.get("bio") or "No bio set"
    aura = prof.get("aura", 0)

    profile_text = (
        f"<b>{html.escape(name)}</b>\n\n"
        f"🔥 <b>Aura:</b> {aura}\n"
        "👥 <b>Followers:</b> 0 | <b>Following:</b> 0\n\n"
        f"<i>{html.escape(bio)}</i>"
    )

    if message_id:
        try:
            bot.edit_message_text(
                profile_text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=profile_inline_markup(),
                parse_mode="HTML"
            )
            return
        except Exception:
            pass

    bot.send_message(chat_id, profile_text, reply_markup=profile_inline_markup(), parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def handle_profile_button(message):
    show_my_profile(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "ℹ Help")
def handle_help_button(message):
    help_text = (
        "ℹ <b>BDU Confessions Help</b>\n\n"
        "• Tap <b>✍️ Confess</b> to submit a secret or campus story.\n"
        "• Submissions and comments are 100% anonymous.\n"
        "• Respect community guidelines: No names, no doxxing, no hate speech."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=main_menu_keyboard(), parse_mode="HTML")

# ---------- MEDIA & TEXT COMMENT / PROFILE HANDLER ----------

@bot.message_handler(content_types=['text', 'sticker', 'animation', 'document'], func=lambda m: m.chat.type == 'private')
def handle_incoming_messages(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "target_confession": None, "reply_to_idx": None
    })

    # Changing Nickname
    if user.get("state") == "WAITING_NICKNAME":
        if message.content_type != "text":
            bot.send_message(uid, "Please send a text message for your nickname.", parse_mode="HTML")
            return
        new_nick = message.text.strip()
        if len(new_nick) > 25:
            bot.send_message(uid, "Nickname too long (max 25 characters). Please try another:")
            return
        update_user_profile(uid, nickname=new_nick)
        user["state"] = "IDLE"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile"))
        bot.send_message(uid, f"✅ Nickname updated to: <b>{html.escape(new_nick)}</b>", reply_markup=markup, parse_mode="HTML")
        return

    # Changing Bio
    elif user.get("state") == "WAITING_BIO":
        if message.content_type != "text":
            bot.send_message(uid, "Please send a text message for your bio.", parse_mode="HTML")
            return
        new_bio = message.text.strip()
        if len(new_bio) > 120:
            bot.send_message(uid, "Bio too long (max 120 characters). Please enter a shorter bio:")
            return
        update_user_profile(uid, bio=new_bio)
        user["state"] = "IDLE"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile"))
        bot.send_message(uid, f"✅ Bio updated!", reply_markup=markup, parse_mode="HTML")
        return

    # Confession submission text
    elif user.get("state") == "WAITING_TEXT":
        if message.content_type != "text":
            bot.send_message(uid, "⚠ Confessions must be sent as text.", parse_mode="HTML")
            return

        raw_text = message.text.strip()
        if len(raw_text) < 10:
            bot.send_message(uid, "⚠️ Your confession is too short. Please provide at least 10 characters.", parse_mode="HTML")
            return
        if len(raw_text) > 1500:
            bot.send_message(uid, "⚠️ Your confession exceeds the 1,500 character limit.", parse_mode="HTML")
            return

        user["text"] = raw_text
        user["state"] = "PREVIEW"

        preview_body = html.escape(raw_text)
        preview_text = (
            "Here is a preview of your confession:\n\n"
            f"<i>{preview_body}</i>\n\n"
            "Please review it and choose an option below."
        )
        bot.send_message(uid, preview_text, reply_markup=preview_inline_markup(), parse_mode="HTML")

    # Comment submission (text, sticker, native GIF, or document GIF)
    elif user.get("state") == "WAITING_COMMENT":
        target = user.get("target_confession")
        if not target:
            bot.send_message(uid, "Session expired. Please click '💬 View / Add Comments' from the channel again.", reply_markup=main_menu_keyboard(), parse_mode="HTML")
            user["state"] = "IDLE"
            return

        c_key = str(target)
        reply_to = user.get("reply_to_idx")

        new_comment = {
            "sender_id": uid,
            "likes": 0,
            "dislikes": 0,
            "liked_by": [],
            "disliked_by": [],
            "reply_to": reply_to,
            "timestamp": time.strftime("%b %d, %H:%M")
        }

        # 1. Plain text
        if message.content_type == "text":
            new_comment["type"] = "text"
            new_comment["text"] = message.text.strip()

        # 2. Sticker
        elif message.content_type == "sticker" and message.sticker:
            new_comment["type"] = "sticker"
            new_comment["file_id"] = message.sticker.file_id
            new_comment["text"] = "[Sticker]"

        # 3. Native animation / GIF
        elif message.content_type == "animation" and message.animation:
            new_comment["type"] = "animation"
            new_comment["file_id"] = message.animation.file_id
            new_comment["text"] = "[GIF]"

        # 4. Telegram GIF sent as Document
        elif message.content_type == "document" and message.document:
            mime = (message.document.mime_type or "").lower()
            if "gif" in mime or "video" in mime:
                new_comment["type"] = "animation"
                new_comment["file_id"] = message.document.file_id
                new_comment["text"] = "[GIF]"
            else:
                bot.send_message(uid, "⚠️ Only Text, Stickers, and GIFs are supported as comments.", parse_mode="HTML")
                return
        else:
            bot.send_message(uid, "⚠️ Unsupported comment format. Please send Text, Sticker, or GIF.", parse_mode="HTML")
            return

        # Save to database
        store = load_comments_store()
        if c_key not in store or not isinstance(store[c_key], list):
            if isinstance(store.get(c_key), dict):
                store[c_key] = store[c_key].get("comments", [])
            else:
                store[c_key] = []

        store[c_key].append(new_comment)
        save_comments_store(store)

        # 1 comment = +1 Aura
        update_user_profile(uid, aura_delta=1)

        # Real-time counter update on the channel post
        update_channel_comment_count(c_key)

        user["state"] = "IDLE"
        user["reply_to_idx"] = None

        bot.send_message(uid, "✅ <b>Your anonymous comment has been posted!</b>", reply_markup=main_menu_keyboard(), parse_mode="HTML")
        display_browse_comments(uid, c_key)

# ---------- INLINE CALLBACK HANDLERS ----------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.message.chat.id
    data = call.data
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "target_confession": None, "reply_to_idx": None
    })

    # Profile Navigation
    if data == "prof_edit":
        bot.edit_message_text(
            "<b>Edit Profile Settings:</b>\nChoose an action below:",
            chat_id=uid,
            message_id=call.message.message_id,
            reply_markup=edit_profile_inline_markup(),
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)

    elif data == "edit_prof_nick":
        user["state"] = "WAITING_NICKNAME"
        bot.send_message(uid, "✏️ Enter your new nickname (max 25 characters):", reply_markup=cancel_reply_keyboard())
        bot.answer_callback_query(call.id)

    elif data == "edit_prof_bio":
        user["state"] = "WAITING_BIO"
        bot.send_message(uid, "📝 Enter your new bio (max 120 characters):", reply_markup=cancel_reply_keyboard())
        bot.answer_callback_query(call.id)

    elif data == "back_to_profile":
        show_my_profile(uid, chat_id=uid, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)

    # Hub Action: Add Comment
    elif data.startswith("hub_add_"):
        c_num = data.replace("hub_add_", "")
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        user["reply_to_idx"] = None

        prompt_msg = (
            f"✍️ <b>Add Your Anonymous Comment for Confession #{c_num}</b>\n\n"
            "You can send your comment as:\n"
            "• 📝 <b>Text message</b>\n"
            "• 🎭 <b>Sticker</b>\n"
            "• 🎬 <b>GIF / Animation</b>\n\n"
            "<i>Everything you post is 100% anonymous!</i>"
        )
        bot.send_message(uid, prompt_msg, reply_markup=cancel_reply_keyboard(), parse_mode="HTML")
        bot.answer_callback_query(call.id)

    # Hub Action: Browse Comments
    elif data.startswith("hub_browse_"):
        c_num = data.replace("hub_browse_", "")
        display_browse_comments(uid, c_num)
        bot.answer_callback_query(call.id)

    elif data == "btn_edit":
        user["state"] = "WAITING_TEXT"
        bot.edit_message_text("Please send the updated text of your confession:", chat_id=uid, message_id=call.message.message_id)

    elif data == "btn_cancel":
        user["state"] = "IDLE"
        user["categories"] = []
        user["text"] = ""
        user["target_confession"] = None
        user["reply_to_idx"] = None
        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass
        bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard(), parse_mode="HTML")

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

        safe_body = html.escape(confession_body)
        admin_card = f"<b>Pending Confession</b>\n\n{safe_body}\n\n{cat_hashtags}"
        bot.send_message(ADMIN_GROUP_ID, admin_card, reply_markup=admin_markup, parse_mode="HTML")

        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass

        rate_limit_cache[uid] = time.time()
        user["state"] = "IDLE"
        user["categories"] = []
        user["text"] = ""

        bot.send_message(uid, "✅ Your confession has been submitted and is pending review.", reply_markup=main_menu_keyboard(), parse_mode="HTML")

    elif data.startswith("adm_rej_"):
        bot.edit_message_text("❌ <b>Submission Rejected.</b>", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("adm_app_"):
        global confession_counter
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
            reply_markup=channel_comment_button(current_num, 0),
            parse_mode="HTML"
        )

        posts = load_posts_map()
        posts[str(current_num)] = {
            "msg_id": channel_msg.message_id,
            "text": body,
            "tags": hashtags
        }
        save_posts_map(posts)

        try:
            bot.send_message(
                int(target_uid),
                f"🎉 <b>Your confession has been approved and published!</b>\n\nIt is now live as <b>Confession #{current_num}</b> on {CHANNEL_ID}.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        bot.edit_message_text(
            f"✅ <b>Published as Confession #{current_num}</b>\n\n{safe_body}\n\n{hashtags}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )

        confession_counter = current_num + 1
        save_counter(confession_counter)

    # Single-vote and toggle logic
    elif data.startswith("like_") or data.startswith("dislike_"):
        action, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        store = load_comments_store()
        c_key = str(c_num)

        raw_entry = store.get(c_key, [])
        if isinstance(raw_entry, dict):
            comments_list = raw_entry.get("comments", [])
        elif isinstance(raw_entry, list):
            comments_list = raw_entry
        else:
            comments_list = []

        if idx < len(comments_list):
            target_c = comments_list[idx]
            if isinstance(target_c, str):
                target_c = {"text": target_c, "liked_by": [], "disliked_by": [], "type": "text"}
                comments_list[idx] = target_c

            if "liked_by" not in target_c or not isinstance(target_c["liked_by"], list):
                target_c["liked_by"] = []
            if "disliked_by" not in target_c or not isinstance(target_c["disliked_by"], list):
                target_c["disliked_by"] = []

            liked_by = target_c["liked_by"]
            disliked_by = target_c["disliked_by"]

            if action == "like":
                if uid in liked_by:
                    bot.answer_callback_query(call.id, "You already liked this comment.")
                    return
                if uid in disliked_by:
                    disliked_by.remove(uid)
                liked_by.append(uid)
                bot.answer_callback_query(call.id, "Liked! 👍🏼")
            else:
                if uid in disliked_by:
                    bot.answer_callback_query(call.id, "You already disliked this comment.")
                    return
                if uid in liked_by:
                    liked_by.remove(uid)
                disliked_by.append(uid)
                bot.answer_callback_query(call.id, "Disliked! 👎🏼")

            target_c["likes"] = len(liked_by)
            target_c["dislikes"] = len(disliked_by)
            save_comments_store(store)

            try:
                bot.edit_message_reply_markup(
                    chat_id=uid,
                    message_id=call.message.message_id,
                    reply_markup=comment_action_markup(c_num, idx, len(liked_by), len(disliked_by))
                )
            except Exception:
                pass

    # Reply to specific comment
    elif data.startswith("rep_"):
        _, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        user["reply_to_idx"] = idx

        store = load_comments_store()
        raw_entry = store.get(str(c_num), [])
        comments_list = raw_entry.get("comments", []) if isinstance(raw_entry, dict) else raw_entry if isinstance(raw_entry, list) else []

        preview_ref = ""
        if idx < len(comments_list):
            c_item = comments_list[idx]
            snippet = c_item if isinstance(c_item, str) else c_item.get("text", "Media")
            preview_ref = f"to: <i>\"{html.escape(str(snippet)[:35])}\"</i>"

        bot.send_message(
            uid,
            f"✍️ <b>Replying {preview_ref}:</b>\n\nSend your text, sticker, or GIF reply:",
            reply_markup=cancel_reply_keyboard(),
            parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)

# --- CLEAN STARTUP & RECOVERY ---
print("BDU Confession Bot Engine starting...")
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook clearance notice: {e}")

# --- AUTO-DUMP RESCUE: Sends comments directly to your admin group ---
try:
    if os.path.exists("confession_comments.json"):
        with open("confession_comments.json", "rb") as f:
            bot.send_document(ADMIN_GROUP_ID, f, caption="🚨 RESCUED COMMENTS FILE")
except Exception as e:
    print(f"Rescue dump error: {e}")

time.sleep(5)
bot.infinity_polling(skip_pending=True)
