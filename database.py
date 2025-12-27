from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["kino_bot"]

users_col = db["users"]
pending_videos_col = db["pending_videos"]
approved_videos_col = db["approved_videos"]
channels_col = db["channels"]
admins_col = db["admins"]

MAIN_ADMIN_ID = 7162630033

if not admins_col.find_one({"user_id": MAIN_ADMIN_ID}):
    admins_col.insert_one({"user_id": MAIN_ADMIN_ID})
