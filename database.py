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
config_col = db["config"]


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
            "is_admin": False,
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


async def get_all_users_list():
    return await get_all_users()


async def get_banned_users_list():
    users = []
    async for user in users_col.find({"is_banned": True}):
        users.append(user)
    return users


async def get_premium_users_list():
    users = []
    async for user in users_col.find({"is_premium": True}):
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
    new_val = not user.get("notifications", True) if user else True
    await users_col.update_one({"user_id": user_id}, {"$set": {"notifications": new_val}})
    return new_val


async def toggle_silent(user_id):
    user = await get_user(user_id)
    new_val = not user.get("silent_mode", False) if user else False
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


async def get_all_feedback():
    feedbacks = []
    async for fb in feedback_col.find({}).sort("date", -1):
        feedbacks.append(fb)
    return feedbacks


async def get_active_users_today():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return await users_col.count_documents({"last_active": {"$gte": today_start}})


async def get_new_users_today():
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return await users_col.count_documents({"joined_date": {"$gte": today_start}})


async def get_top_users(limit=10):
    users = []
    async for user in users_col.find({}).sort("downloads", -1).limit(limit):
        users.append(user)
    return users


async def total_downloads_count():
    return await downloads_col.count_documents({})


async def total_bookmarks_count():
    return await bookmarks_col.count_documents({})


async def search_user(query):
    try:
        q_int = int(query)
        res = await users_col.find_one({"user_id": q_int})
        if res:
            return [res]
    except:
        pass
    results = []
    async for u in users_col.find({"$or": [{"name": {"$regex": query, "$options": "i"}}, {"username": {"$regex": query, "$options": "i"}}]}).limit(10):
        results.append(u)
    return results


async def set_maintenance(status: bool):
    await config_col.update_one({"type": "maintenance"}, {"$set": {"status": status}}, upsert=True)


async def get_maintenance():
    res = await config_col.find_one({"type": "maintenance"})
    return res.get("status", False) if res else False


async def set_fsub_channel(channel: str):
    await config_col.update_one({"type": "fsub"}, {"$set": {"channel": channel}}, upsert=True)


async def get_fsub_channel():
    res = await config_col.find_one({"type": "fsub"})
    return res.get("channel") if res else None


async def delete_fsub():
    await config_col.delete_one({"type": "fsub"})


async def add_admin(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_admin": True}})


async def remove_admin(user_id):
    await users_col.update_one({"user_id": user_id}, {"$set": {"is_admin": False}})


async def is_admin(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("is_admin", False) if user else False


async def get_admins_list():
    admins = []
    async for u in users_col.find({"is_admin": True}):
        admins.append(u)
    return admins


async def clear_all_logs():
    await downloads_col.delete_many({})


async def get_bot_stats():
    total = await total_users()
    active_today = await get_active_users_today()
    new_today = await get_new_users_today()
    premium = await users_col.count_documents({"is_premium": True})
    banned = await users_col.count_documents({"is_banned": True})
    admins = await users_col.count_documents({"is_admin": True})
    downloads = await total_downloads_count()
    return {
        "total": total,
        "active_today": active_today,
        "new_today": new_today,
        "premium": premium,
        "banned": banned,
        "admins": admins,
        "total_downloads": downloads
    }


async def test_connection():
    try:
        await mongo_client.admin.command('ping')
        print("✅ MongoDB Connected!")
        return True
    except Exception as e:
        print(f"❌ MongoDB Failed: {e}")
        return False
    
