import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

MONGO_URL = os.environ.get("MONGO_URL")

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["restricted_bot"]

users_col = db["users"]
downloads_col = db["downloads"]
bookmarks_col = db["bookmarks"]
feedback_col = db["feedback"]


async def add_user(user_id, name, username=None):
    existing = await users_col.find_one({"user_id": user_id})
    if not existing:
        user_data = {
            "user_id": user_id,
            "name": name,
            "username": username,
            "phone": None,
            "session_string": None,
            "caption": None,
            "thumbnail_id": None,
            "prefix": None,
            "suffix": None,
            "language": "en",
            "is_banned": False,
            "is_premium": False,
            "premium_expiry": None,
            "downloads": 0,
            "daily_downloads": 0,
            "last_download_date": None,
            "joined_date": datetime.now(),
            "last_active": datetime.now(),
            "referred_by": None,
            "referral_count": 0,
            "notifications": True,
            "silent_mode": False,
            "favorites": []
        }
        await users_col.insert_one(user_data)
        return True
    return False


async def get_user(user_id):
    return await users_col.find_one({"user_id": user_id})


async def update_user(user_id, data):
    await users_col.update_one({"user_id": user_id}, {"$set": data})


async def total_users():
    return await users_col.count_documents({})


async def get_all_users():
    users = []
    async for user in users_col.find({}):
        users.append(user)
    return users


async def is_premium(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user or not user.get("is_premium"):
        return False
    expiry = user.get("premium_expiry")
    if expiry and expiry < datetime.now():
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"is_premium": False, "premium_expiry": None}}
        )
        return False
    return True


async def add_premium(user_id, days=30):
    expiry = datetime.now() + timedelta(days=days)
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": True, "premium_expiry": expiry}}
    )


async def remove_premium(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": False, "premium_expiry": None}}
    )


async def is_banned(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("is_banned", False) if user else False


async def ban_user(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_banned": True}})


async def unban_user(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_banned": False}})


async def check_daily_limit(user_id, limit=10):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        return True, 0
    today = datetime.now().date()
    last_date = user.get("last_download_date")
    if last_date and last_date.date() == today:
        current = user.get("daily_downloads", 0)
        if current >= limit:
            return False, current
        return True, current
    else:
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"daily_downloads": 0, "last_download_date": datetime.now()}}
        )
        return True, 0


async def increment_daily(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"downloads": 1, "daily_downloads": 1},
            "$set": {"last_download_date": datetime.now(), "last_active": datetime.now()}
        }
    )


async def save_session(user_id, session_string, phone):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": session_string, "phone": phone}}
    )


async def get_session(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("session_string") if user else None


async def delete_session(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": None, "phone": None}}
    )


async def set_caption(user_id, caption):
    await users_col.update_one({"user_id": user_id}, {"$set": {"caption": caption}})


async def get_caption(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("caption") if user else None


async def del_caption(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"caption": None}})


async def set_thumbnail(user_id, file_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"thumbnail_id": file_id}})


async def get_thumbnail(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("thumbnail_id") if user else None


async def del_thumbnail(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"thumbnail_id": None}})


async def set_prefix(user_id, prefix):
    await users_col.update_one({"user_id": user_id}, {"$set": {"prefix": prefix}})


async def get_prefix(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("prefix") if user else None


async def set_suffix(user_id, suffix):
    await users_col.update_one({"user_id": user_id}, {"$set": {"suffix": suffix}})


async def get_suffix(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("suffix") if user else None


async def add_download(user_id, link, file_type):
    await downloads_col.insert_one({
        "user_id": user_id,
        "link": link,
        "type": file_type,
        "date": datetime.now()
    })


async def get_history(user_id, limit=10):
    history = []
    async for item in downloads_col.find({"user_id": user_id}).sort("date", -1).limit(limit):
        history.append(item)
    return history


async def clear_history(user_id):
    await downloads_col.delete_many({"user_id": user_id})


async def add_bookmark(user_id, link, tag=None):
    await bookmarks_col.insert_one({
        "user_id": user_id,
        "link": link,
        "tag": tag,
        "date": datetime.now()
    })


async def get_bookmarks(user_id):
    bookmarks = []
    async for item in bookmarks_col.find({"user_id": user_id}).sort("date", -1):
        bookmarks.append(item)
    return bookmarks


async def delete_bookmark(user_id, link):
    await bookmarks_col.delete_one({"user_id": user_id, "link": link})


async def add_favorite(user_id, channel):
    await users_col.update_one(
        {"user_id": user_id},
        {"$addToSet": {"favorites": channel}}
    )


async def get_favorites(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("favorites", []) if user else []


async def remove_favorite(user_id, channel):
    await users_col.update_one(
        {"user_id": user_id},
        {"$pull": {"favorites": channel}}
    )


async def set_language(user_id, lang):
    await users_col.update_one({"user_id": user_id}, {"$set": {"language": lang}})


async def toggle_notifications(user_id):
    user = await get_user(user_id)
    new_val = not user.get("notifications", True)
    await users_col.update_one({"user_id": user_id}, {"$set": {"notifications": new_val}})
    return new_val


async def toggle_silent(user_id):
    user = await get_user(user_id)
    new_val = not user.get("silent_mode", False)
    await users_col.update_one({"user_id": user_id}, {"$set": {"silent_mode": new_val}})
    return new_val


async def reset_settings(user_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "caption": None,
            "thumbnail_id": None,
            "prefix": None,
            "suffix": None,
            "language": "en",
            "notifications": True,
            "silent_mode": False
        }}
    )


async def add_referral(referrer_id, new_user_id):
    await users_col.update_one(
        {"user_id": new_user_id},
        {"$set": {"referred_by": referrer_id}}
    )
    await users_col.update_one(
        {"user_id": referrer_id},
        {"$inc": {"referral_count": 1}}
    )


async def add_feedback(user_id, message):
    await feedback_col.insert_one({
        "user_id": user_id,
        "message": message,
        "date": datetime.now()
    })


async def test_connection():
    try:
        await mongo_client.admin.command('ping')
        print("✅ MongoDB Connected!")
        return True
    except Exception as e:
        print(f"❌ MongoDB Failed: {e}")
        return False
