from pymongo import MongoClient
import os

MONGO_URI = "mongodb+srv://ytshohrux1_db_user:s2fFP6UE7QFpDr3E@cluster0.eo1vapi.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["kino_bot"]

# Kolleksiyalar
users_col = db["users"]
pending_videos_col = db["pending_videos"]
approved_videos_col = db["approved_videos"]
channels_col = db["channels"]
admins_col = db["admins"]

# Asosiy admin
MAIN_ADMIN_ID = 7162630033

# Dastlabki adminni qo'shish
if not admins_col.find_one({"user_id": MAIN_ADMIN_ID}):
    admins_col.insert_one({"user_id": MAIN_ADMIN_ID})
