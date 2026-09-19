import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Optional
from config import DATA_DIR

class Database:
    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or DATA_DIR / "data_store.json"
        self._lock = asyncio.Lock()
        
        # State caches
        self.banned_users: Set[str] = set()
        self.muted_users: Set[str] = set()
        self.muted_until: Dict[str, str] = {}
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
                    self.muted_until = data.get("muted_until", {}) or {}
                    self.messages = data.get("messages", [])[-500:]
                    self.known_users = data.get("known_users", {})
                    # Backfill contacts from existing visitor messages.
                    for m in self.messages:
                        if not m.get("is_developer") and m.get("sender_id"):
                            uid = str(m.get("sender_id"))
                            self.known_users.setdefault(uid, {"id": uid, "name": m.get("sender_name") or "زائر"})
        except Exception as e:
            print(f"[DB] Error loading data: {e}")

    def save(self):
        try:
            data = {
                "banned_users": list(self.banned_users),
                "muted_users": list(self.muted_users),
                "muted_until": self.muted_until,
                "messages": self.messages[-500:],
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

    async def mute_user(self, user_id: str, minutes: Optional[int] = None):
        async with self._lock:
            uid = str(user_id)
            self.muted_users.add(uid)
            if minutes is None:
                self.muted_until.pop(uid, None)
            else:
                self.muted_until[uid] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
            self.save()

    async def unmute_user(self, user_id: str):
        async with self._lock:
            uid = str(user_id)
            self.muted_users.discard(uid)
            self.muted_until.pop(uid, None)
            self.save()

    async def is_muted(self, user_id: str) -> bool:
        uid = str(user_id)
        if uid not in self.muted_users:
            return False
        until = self.muted_until.get(uid)
        if until:
            try:
                if datetime.now() >= datetime.fromisoformat(until):
                    await self.unmute_user(uid)
                    return False
            except Exception:
                pass
        return True

    async def mute_remaining(self, user_id: str) -> str:
        uid = str(user_id)
        if not await self.is_muted(uid):
            return ""
        until = self.muted_until.get(uid)
        if not until:
            return "دائم"
        try:
            seconds = max(0, int((datetime.fromisoformat(until) - datetime.now()).total_seconds()))
            if seconds >= 86400:
                return f"{seconds // 86400} يوم"
            if seconds >= 3600:
                return f"{seconds // 3600} ساعة"
            return f"{max(1, seconds // 60)} دقيقة"
        except Exception:
            return "دائم"

    async def add_active_user(self, session_id: str, user_data: dict):
        async with self._lock:
            self.active_users[session_id] = {
                **user_data,
                "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_seen": datetime.now().strftime("%H:%M:%S"),
                "in_call": False
            }
            uid = str(user_data.get("id", session_id))
            self.known_users[uid] = {"id": uid, "name": user_data.get("name") or "زائر"}
            self.save()

    async def remove_active_user(self, session_id: str):
        async with self._lock:
            if session_id in self.active_users:
                del self.active_users[session_id]

    async def update_user_call_status(self, session_id: str, in_call: bool):
        async with self._lock:
            if session_id in self.active_users:
                self.active_users[session_id]["in_call"] = in_call

    async def add_message(self, message: dict):
        async with self._lock:
            message["timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.messages.append(message)
            if not message.get("is_developer") and message.get("sender_id"):
                uid = str(message.get("sender_id"))
                self.known_users[uid] = {"id": uid, "name": message.get("sender_name") or "زائر"}
            if len(self.messages) > 500:
                self.messages.pop(0)
            self.save()

    async def get_recent_messages(self, limit: int = 50, user_id: Optional[str] = None) -> List[dict]:
        messages = self.messages
        if user_id is not None:
            uid = str(user_id)
            messages = [m for m in messages if str(m.get("sender_id")) == uid or str(m.get("target_id", "")) == uid]
        return messages[-limit:]

    async def remember_user(self, user_id: str, name: str):
        async with self._lock:
            uid = str(user_id)
            self.known_users[uid] = {"id": uid, "name": name or "زائر"}
            self.save()

    async def get_contacts(self) -> List[dict]:
        contacts = []
        for uid, info in self.known_users.items():
            active = self.active_users.get(uid)
            contacts.append({
                "id": uid,
                "name": (active or info).get("name", "زائر"),
                "online": active is not None,
                "in_call": bool(active and active.get("in_call")),
                "joined_at": active.get("joined_at", "") if active else "",
            })
        return contacts

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
