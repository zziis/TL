import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional

class Database:
    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or Path(__file__).resolve().parent / "data_store.json"
        self._lock = asyncio.Lock()
        
        # State caches
        self.banned_users: Set[str] = set()
        self.muted_users: Set[str] = set()
        self.active_users: Dict[str, dict] = {}  # session_id -> {id, name, username, ip, joined_at, last_seen, in_call}
        self.messages: List[dict] = []
        self.known_users: Dict[str, dict] = {}
        self.active_calls: Dict[str, dict] = {}  # call_id -> {user_id, user_name, type: 'voice'|'video', status: 'pending'|'accepted'|'rejected'|'ended', started_at}
        
        self.load()

    def load(self):
        try:
            if self.data_file.exists():
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.banned_users = set(data.get("banned_users", []))
                    self.muted_users = set(data.get("muted_users", []))
                    self.messages = data.get("messages", [])[-100:]  # Keep last 100
                    self.known_users = data.get("known_users", {})
        except Exception as e:
            print(f"[DB] Error loading data: {e}")

    def save(self):
        try:
            data = {
                "banned_users": list(self.banned_users),
                "muted_users": list(self.muted_users),
                "messages": self.messages[-100:],
                "known_users": self.known_users
            }
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DB] Error saving data: {e}")

    async def ban_user(self, user_id: str):
        async with self._lock:
            self.banned_users.add(str(user_id))
            if str(user_id) in self.muted_users:
                self.muted_users.remove(str(user_id))
            self.save()

    async def unban_user(self, user_id: str):
        async with self._lock:
            if str(user_id) in self.banned_users:
                self.banned_users.remove(str(user_id))
                self.save()

    async def is_banned(self, user_id: str) -> bool:
        return str(user_id) in self.banned_users

    async def mute_user(self, user_id: str):
        async with self._lock:
            self.muted_users.add(str(user_id))
            self.save()

    async def unmute_user(self, user_id: str):
        async with self._lock:
            if str(user_id) in self.muted_users:
                self.muted_users.remove(str(user_id))
                self.save()

    async def is_muted(self, user_id: str) -> bool:
        return str(user_id) in self.muted_users

    async def add_active_user(self, session_id: str, user_data: dict):
        async with self._lock:
            now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_time = datetime.now().strftime("%H:%M:%S")
            previous = self.known_users.get(str(session_id), {})
            record = {
                **previous,
                **user_data,
                "id": str(session_id),
                "joined_at": previous.get("joined_at", now_full),
                "last_seen": now_time,
                "online": True,
                "in_call": previous.get("in_call", False)
            }
            self.active_users[str(session_id)] = record.copy()
            self.known_users[str(session_id)] = record.copy()
            self.save()

    async def remove_active_user(self, session_id: str):
        async with self._lock:
            sid = str(session_id)
            if sid in self.active_users:
                del self.active_users[sid]
            if sid in self.known_users:
                self.known_users[sid]["online"] = False
                self.known_users[sid]["last_seen"] = datetime.now().strftime("%H:%M:%S")
                self.save()

    async def touch_user(self, user_id: str, name: str):
        async with self._lock:
            uid = str(user_id)
            rec = self.known_users.get(uid, {"id": uid, "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            rec.update({"id": uid, "name": name, "last_seen": datetime.now().strftime("%H:%M:%S"), "online": uid in self.active_users})
            self.known_users[uid] = rec
            self.save()

    async def get_users_for_admin(self) -> List[dict]:
        users = []
        for uid, rec in self.known_users.items():
            item = dict(rec)
            item["online"] = uid in self.active_users
            if uid in self.active_users:
                item.update(self.active_users[uid])
                item["online"] = True
            users.append(item)
        users.sort(key=lambda x: x.get("last_seen", ""), reverse=True)
        return users

    async def update_user_call_status(self, session_id: str, in_call: bool):
        async with self._lock:
            if session_id in self.active_users:
                self.active_users[session_id]["in_call"] = in_call

    async def add_message(self, message: dict):
        async with self._lock:
            message["timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.messages.append(message)
            if len(self.messages) > 100:
                self.messages.pop(0)
            self.save()

    async def get_recent_messages(self, limit: int = 50, user_id: Optional[str] = None) -> List[dict]:
        messages = self.messages
        if user_id is not None:
            uid = str(user_id)
            messages = [m for m in messages if str(m.get("sender_id")) == uid or str(m.get("target_id", "")) == uid]
        return messages[-limit:]

    async def create_call(self, call_id: str, user_id: str, user_name: str, call_type: str) -> dict:
        async with self._lock:
            call_info = {
                "call_id": call_id,
                "user_id": user_id,
                "user_name": user_name,
                "type": call_type,  # 'voice' | 'video'
                "status": "pending",
                "created_at": datetime.now().strftime("%H:%M:%S")
            }
            self.active_calls[call_id] = call_info
            return call_info

    async def update_call_status(self, call_id: str, status: str):
        async with self._lock:
            if call_id in self.active_calls:
                self.active_calls[call_id]["status"] = status

    async def get_active_call(self, call_id: str) -> Optional[dict]:
        return self.active_calls.get(call_id)

db = Database()
