import os
import json
import html
import time
from threading import Thread, Lock
from flask import Flask
import telebot
from telebot import types

# ---------------- CONFIGURATION ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8709978309:AAHlT2HMXwyDkRR181F4SMvIRX8hrVvwGgo")
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
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

keep_alive()

# --- REPOSITORY STORAGE FILES ---
COUNTER_FILE = "confession_count.txt"
COMMENTS_FILE = "confession_comments.json"
POSTS_MAP_FILE = "confession_posts.json"

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
        types.InlineKeyboardButton("✍️ Edit", callback_data="btn_edit")
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
    markup.row(types.InlineKeyboardButton("✍️ Edit Profile", callback_data="prof_edit"))
    markup.row(types.InlineKeyboardButton("📑 My Confessions", callback_data="prof_confessions"),
               types.InlineKeyboardButton("💬 My Comments", callback_data="prof_comments"))
    markup.row(types.InlineKeyboardButton("👥 Following", callback_data="prof_following"),
               types.InlineKeyboardButton("👥 Followers", callback_data="prof_followers"))
    markup.row(types.InlineKeyboardButton("⚙️ Settings", callback_data="prof_settings"))
    markup.row(types.InlineKeyboardButton("💬 My Chats", callback_data="prof_chats"))
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
        types.InlineKeyboardButton(f"👍 {likes}", callback_data=f"like_{c_num}_{c_idx}"),
        types.InlineKeyboardButton(f"👎 {dislikes}", callback_data=f"dislike_{c_num}_{c_idx}"),
        types.InlineKeyboardButton("↩️ Reply", callback_data=f"rep_{c_num}_{c_idx}")
    )
    return markup

# ---------- REAL-TIME CHANNEL BUTTON UPDATE ----------

def update_channel_comment_count(c_num):
    c_key = str(c_num)
    posts = load_posts_map()
    msg_id = posts.get(c_key)
    
    comments_store = load_comments_store()
    comments_list = comments_store.get(c_key, [])
    if isinstance(comments_list, dict):
        comments_list = comments_list.get("comments", [])
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
    comments_store = load_comments_store()
    comments_list = comments_store.get(c_key, [])
    if isinstance(comments_list, dict):
        comments_list = comments_list.get("comments", [])
    count = len(comments_list)

    hub_text = (
        f"📖 <b>Confession #{c_num}</b>\n\n"
        f"💬 <i>Join the anonymous discussion! You can read what others said or share your own thoughts anonymously.</i>"
    )
    bot.send_message(chat_id, hub_text, reply_markup=confession_hub_markup(c_num, count))

def display_browse_comments(chat_id, c_num):
    c_key = str(c_num)
    comments_store = load_comments_store()
    comments_list = comments_store.get(c_key, [])
    if isinstance(comments_list, dict):
        comments_list = comments_list.get("comments", [])
    total = len(comments_list)

    if total == 0:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Add the First Comment", callback_data=f"hub_add_{c_num}"))
        bot.send_message(
            chat_id,
            f"💬 <b>Comments for Confession #{c_num}</b>\n\nNo comments yet! Be the first to share your thoughts anonymously.",
            reply_markup=markup
        )
        return

    bot.send_message(chat_id, f"💬 <b>Discussion for Confession #{c_num} ({total} comments):</b>")

    for idx, c in enumerate(comments_list):
        c_type = c.get("type", "text")
        reply_to_idx = c.get("reply_to")
        reply_header = ""
        if reply_to_idx is not None and reply_to_idx < len(comments_list):
            ref_c = comments_list[reply_to_idx]
            ref_snippet = ref_c.get("text", "Media")
            if len(ref_snippet) > 25:
                ref_snippet = ref_snippet[:22] + "..."
            reply_header = f"⤷ <i>In reply to #{reply_to_idx + 1}: \"{html.escape(ref_snippet)}\"</i>\n"

        safe_date = html.escape(c.get("timestamp", ""))
        date_str = f" • <small>{safe_date}</small>" if safe_date else ""
        user_info = f"👤 <b>Anonymous</b> ⚡️ {c.get('aura', 0)} Aura{date_str}"

        # If it's a sticker comment
        if c_type == "sticker":
            bot.send_message(chat_id, f"{reply_header}#{idx + 1} {user_info}:")
            bot.send_sticker(chat_id, c["file_id"])
            bot.send_message(
                chat_id,
                f"Actions for comment #{idx + 1}:",
                reply_markup=comment_action_markup(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
            )

        # If it's a GIF comment
        elif c_type == "animation":
            bot.send_message(chat_id, f"{reply_header}#{idx + 1} {user_info}:")
            bot.send_animation(chat_id, c["file_id"])
            bot.send_message(
                chat_id,
                f"Actions for comment #{idx + 1}:",
                reply_markup=comment_action_markup(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
            )

        # Standard text comment
        else:
            safe_text = html.escape(c.get("text", ""))
            text = (
                f"{reply_header}"
                f"#{idx + 1} 💬 \"{safe_text}\"\n\n"
                f"{user_info}"
            )
            bot.send_message(
                chat_id,
                text,
                reply_markup=comment_action_markup(c_num, idx, c.get("likes", 0), c.get("dislikes", 0))
            )

    bottom_markup = types.InlineKeyboardMarkup()
    bottom_markup.add(types.InlineKeyboardButton("➕ Add Your Comment", callback_data=f"hub_add_{c_num}"))
    bot.send_message(chat_id, f"Displayed {total} comment(s).", reply_markup=bottom_markup)

# ---------- START COMMAND & DEEP LINKING ----------

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "aura": 0, "target_confession": None, "reply_to_idx": None
    })

    raw_text = message.text or ""
    parts = raw_text.strip().split()

    # Deep-link clicked from channel: /start comm_X
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
            print(f"[Error] Deep-link redirection error: {e}")

    user["state"] = "IDLE"
    welcome_text = "Welcome! Use Confess to submit confessions"
    bot.send_message(uid, welcome_text, reply_markup=main_menu_keyboard())

# ---------- MAIN MENU BUTTONS ----------

@bot.message_handler(func=lambda m: m.text == "✍️ Confess")
def handle_confess_button(message):
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
    user["reply_to_idx"] = None
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
        users_data[uid]["reply_to_idx"] = None
    bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def handle_profile_button(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {"aura": 0})
    profile_text = (
        "<b>None Anonymous</b>\n\n"
        f"⚡️ <b>Aura:</b> {user.get('aura', 0)}\n"
        "👥 <b>Followers:</b> 0 | <b>Following:</b> 0\n\n"
        "<i>No bio set</i>"
    )
    bot.send_message(uid, profile_text, reply_markup=profile_inline_markup())

@bot.message_handler(func=lambda m: m.text == "ℹ️ Help")
def handle_help_button(message):
    help_text = (
        "ℹ️ <b>BDU Confessions Help</b>\n\n"
        "• Tap <b>✍️ Confess</b> to submit a secret or campus story.\n"
        "• Submissions and comments are 100% anonymous.\n"
        "• Respect community guidelines: No names, no doxxing, no hate speech."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=main_menu_keyboard())

# ---------- MEDIA & TEXT COMMENT HANDLER ----------

@bot.message_handler(content_types=['text', 'sticker', 'animation'], func=lambda m: m.chat.type == 'private')
def handle_incoming_messages(message):
    uid = message.chat.id
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "aura": 0, "target_confession": None, "reply_to_idx": None
    })

    # Confession submission text
    if user.get("state") == "WAITING_TEXT":
        if message.content_type != "text":
            bot.send_message(uid, "⚠️️ Confessions must be sent as text.")
            return

        raw_text = message.text.strip()
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
        bot.send_message(uid, preview_text, reply_markup=preview_inline_markup())

    # Comment submission (text, sticker, or GIF)
    elif user.get("state") == "WAITING_COMMENT":
        target = user.get("target_confession")
        if not target:
            bot.send_message(uid, "Session expired. Please click '💬 View / Add Comments' from the channel again.", reply_markup=main_menu_keyboard())
            user["state"] = "IDLE"
            return

        c_key = str(target)
        reply_to = user.get("reply_to_idx")

        # Build comment object
        new_comment = {
            "aura": user.get("aura", 0),
            "likes": 0,
            "dislikes": 0,
            "reply_to": reply_to,
            "timestamp": time.strftime("%b %d, %H:%M")
        }

        if message.content_type == "text":
            new_comment["type"] = "text"
            new_comment["text"] = message.text.strip()
        elif message.content_type == "sticker":
            new_comment["type"] = "sticker"
            new_comment["file_id"] = message.sticker.file_id
            new_comment["text"] = "[Sticker]"
        elif message.content_type == "animation":
            new_comment["type"] = "animation"
            new_comment["file_id"] = message.animation.file_id
            new_comment["text"] = "[GIF]"

        # Save to database
        store = load_comments_store()
        if c_key not in store or not isinstance(store[c_key], list):
            store[c_key] = []
        store[c_key].append(new_comment)
        save_comments_store(store)

        # Real-time counter update on the public channel post!
        update_channel_comment_count(c_key)

        user["aura"] = user.get("aura", 0) + 2
        user["state"] = "IDLE"
        user["reply_to_idx"] = None

        bot.send_message(uid, "✅ <b>Your anonymous comment has been posted!</b>", reply_markup=main_menu_keyboard())
        display_browse_comments(uid, c_key)

# ---------- INLINE CALLBACK HANDLERS ----------

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    uid = call.message.chat.id
    data = call.data
    user = users_data.setdefault(uid, {
        "state": "IDLE", "text": "", "categories": [],
        "aura": 0, "target_confession": None, "reply_to_idx": None
    })

    # Hub Action: Add Comment
    if data.startswith("hub_add_"):
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
        bot.send_message(uid, prompt_msg, reply_markup=cancel_reply_keyboard())
        bot.answer_callback_query(call.id)

    # Hub Action: Browse Comments
    elif data.startswith("hub_browse_"):
        c_num = data.replace("hub_browse_", "")
        display_browse_comments(uid, c_num)
        bot.answer_callback_query(call.id)

    # Confession drafting
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
        bot.send_message(uid, "Action cancelled. You are back at the main menu.", reply_markup=main_menu_keyboard())

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
        bot.send_message(ADMIN_GROUP_ID, admin_card, reply_markup=admin_markup)

        try:
            bot.delete_message(chat_id=uid, message_id=call.message.message_id)
        except Exception:
            pass

        rate_limit_cache[uid] = time.time()
        user["aura"] = user.get("aura", 0) + 5
        user["state"] = "IDLE"
        user["categories"] = []
        user["text"] = ""

        bot.send_message(uid, "✅ Your confession has been submitted and is pending review.", reply_markup=main_menu_keyboard())

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
            reply_markup=channel_comment_button(current_num, 0)
        )

        # Store channel post mapping
        posts = load_posts_map()
        posts[str(current_num)] = channel_msg.message_id
        save_posts_map(posts)

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

        confession_counter = current_num + 1
        save_counter(confession_counter)

    # Likes & Dislikes
    elif data.startswith("like_") or data.startswith("dislike_"):
        action, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        store = load_comments_store()
        c_key = str(c_num)

        comments_list = store.get(c_key, [])
        if idx < len(comments_list):
            if action == "like":
                comments_list[idx]["likes"] = comments_list[idx].get("likes", 0) + 1
            else:
                comments_list[idx]["dislikes"] = comments_list[idx].get("dislikes", 0) + 1
            save_comments_store(store)

            c = comments_list[idx]
            bot.edit_message_reply_markup(
                chat_id=uid,
                message_id=call.message.message_id,
                reply_markup=comment_action_markup(c_num, idx, c["likes"], c["dislikes"])
            )
            bot.answer_callback_query(call.id, "Reaction recorded!")

    # Reply to specific comment
    elif data.startswith("rep_"):
        _, c_num, idx_str = data.split("_")
        idx = int(idx_str)
        user["state"] = "WAITING_COMMENT"
        user["target_confession"] = str(c_num)
        user["reply_to_idx"] = idx

        store = load_comments_store()
        comments_list = store.get(str(c_num), [])
        preview_ref = ""
        if idx < len(comments_list):
            snippet = comments_list[idx].get("text", "Media")
            preview_ref = f"to comment #{idx + 1} (<i>\"{html.escape(snippet[:30])}\"</i>)"

        bot.send_message(
            uid,
            f"✍️ <b>Replying {preview_ref}:</b>\n\nSend your text, sticker, or GIF reply:",
            reply_markup=cancel_reply_keyboard()
        )
        bot.answer_callback_query(call.id)

# --- CLEAN STARTUP & RECOVERY ---
print("BDU Confession Bot Engine starting...")
try:
    bot.remove_webhook()
except Exception as e:
    print(f"Webhook clearance notice: {e}")

time.sleep(5)
bot.infinity_polling(skip_pending=True)
