import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import (
    BASE_DIR, UPLOAD_DIR, STATIC_DIR, 
    ADMIN_SECRET_KEY, BOT_TOKEN, DEVELOPER_ID
)
from database import db
from bot import notify_admin_call_request

app = FastAPI(title="Shabah Telegram Platform", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and uploads
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ----------------------------------------------------
# HTTP Routes
# ----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path)


@app.get("/ghost-admin", response_class=HTMLResponse)
async def get_admin(secret: Optional[str] = Query(None)):
    if secret != ADMIN_SECRET_KEY:
        # Simple security barrier
        return HTMLResponse(
            """
            <html dir="rtl" style="background:#07070d;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;">
                <h1 style="color:#ff0077;">💀 وصول محمي لمنصة شبح</h1>
                <p>كلمة السر غير صحيحة أو مفقودة.</p>
                <form method="get" action="/ghost-admin">
                    <input type="password" name="secret" placeholder="أدخل كلمة السر" style="padding:10px 15px;border-radius:8px;border:1px solid #00f3ff;background:#111;color:#fff;margin:10px;">
                    <button type="submit" style="padding:10px 20px;border-radius:8px;background:#00f3ff;color:#000;font-weight:bold;border:none;cursor:pointer;">دخول</button>
                </form>
            </html>
            """,
            status_code=401
        )
    admin_path = STATIC_DIR / "admin" / "index.html"
    return FileResponse(admin_path)


@app.post("/api/upload-voice")
async def upload_voice(file: UploadFile = File(...), user_id: str = Form(...)):
    if await db.is_banned(user_id) or await db.is_muted(user_id):
        raise HTTPException(status_code=403, detail="User is muted or banned")
    
    file_ext = ".webm"
    filename = f"voice_{uuid.uuid4().hex[:10]}{file_ext}"
    target_path = UPLOAD_DIR / filename
    
    contents = await file.read()
    with open(target_path, "wb") as f:
        f.write(contents)
        
    return {"file_url": f"/uploads/{filename}"}


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...), user_id: str = Form(...)):
    if await db.is_banned(user_id) or await db.is_muted(user_id):
        raise HTTPException(status_code=403, detail="User is muted or banned")
    
    filename = f"img_{uuid.uuid4().hex[:10]}.jpg"
    target_path = UPLOAD_DIR / filename
    
    contents = await file.read()
    with open(target_path, "wb") as f:
        f.write(contents)
        
    return {"file_url": f"/uploads/{filename}"}


# ----------------------------------------------------
# WebSocket Connection Manager & Signaling
# ----------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_visitors: Dict[str, WebSocket] = {}
        self.dev_socket: Optional[WebSocket] = None

    async def connect_visitor(self, user_id: str, websocket: WebSocket, name: str):
        await websocket.accept()
        self.active_visitors[user_id] = websocket
        await db.add_active_user(user_id, {"id": user_id, "name": name})
        await self.broadcast_users_to_dev()

    async def disconnect_visitor(self, user_id: str):
        if user_id in self.active_visitors:
            del self.active_visitors[user_id]
        await db.remove_active_user(user_id)
        await self.broadcast_users_to_dev()

    async def connect_developer(self, websocket: WebSocket):
        await websocket.accept()
        self.dev_socket = websocket
        await self.broadcast_users_to_dev()

    def disconnect_developer(self):
        self.dev_socket = None

    async def send_to_user(self, user_id: str, message: dict):
        if user_id in self.active_visitors:
            try:
                await self.active_visitors[user_id].send_json(message)
            except Exception:
                pass

    async def send_to_dev(self, message: dict):
        if self.dev_socket:
            try:
                await self.dev_socket.send_json(message)
            except Exception:
                pass

    async def broadcast_users_to_dev(self):
        if self.dev_socket:
            users_data = await db.get_users_for_admin()
            await self.send_to_dev({
                "type": "users_update",
                "users": users_data
            })

manager = ConnectionManager()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    name: str = Query("زائر"),
    is_dev: bool = Query(False),
    secret: Optional[str] = Query(None)
):
    # Developer Connection
    if is_dev:
        if secret != ADMIN_SECRET_KEY:
            await websocket.close(code=1008)
            return
        await manager.connect_developer(websocket)
        # Send history
        history = await db.get_recent_messages()
        await manager.send_to_dev({"type": "history", "messages": history})

        try:
            while True:
                data = await websocket.receive_json()
                action = data.get("action")

                if action == "send_message":
                    target_id = str(data.get("target_id") or "")
                    if not target_id:
                        continue
                    msg_obj = {
                        "sender_id": "shabah_dev",
                        "sender_name": "شبح",
                        "is_developer": True,
                        "target_id": target_id,
                        "msg_type": data.get("msg_type", "text"),
                        "content": data.get("content", ""),
                        "file_url": data.get("file_url")
                    }
                    await db.add_message(msg_obj)
                    await manager.send_to_dev({"type": "chat", "message": msg_obj})
                    await manager.send_to_user(target_id, {"type": "chat", "message": msg_obj})

                elif action == "call_accept":
                    target_id = data.get("target_id")
                    call_id = data.get("call_id")
                    await db.update_call_status(call_id, "accepted")
                    await db.update_user_call_status(target_id, True)
                    await manager.send_to_user(target_id, {"type": "call_accepted", "call_id": call_id})
                    await manager.broadcast_users_to_dev()

                elif action == "call_reject":
                    target_id = data.get("target_id")
                    call_id = data.get("call_id")
                    await db.update_call_status(call_id, "rejected")
                    await manager.send_to_user(target_id, {"type": "call_rejected", "call_id": call_id})

                elif action == "call_end":
                    target_id = data.get("target_id")
                    call_id = data.get("call_id")
                    if target_id:
                        await db.update_user_call_status(target_id, False)
                        await manager.send_to_user(target_id, {"type": "call_ended", "call_id": call_id})
                    await manager.broadcast_users_to_dev()

                elif action == "webrtc_answer":
                    target_id = data.get("target_id")
                    await manager.send_to_user(target_id, {
                        "type": "webrtc_answer",
                        "sdp": data.get("sdp")
                    })

                elif action == "webrtc_ice":
                    target_id = data.get("target_id")
                    await manager.send_to_user(target_id, {
                        "type": "webrtc_ice",
                        "candidate": data.get("candidate")
                    })

                elif action == "toggle_mask":
                    target_id = data.get("target_id")
                    await manager.send_to_user(target_id, {
                        "type": "mask_toggled",
                        "enabled": data.get("enabled", True)
                    })

                # Moderation Commands
                elif action == "mod_mute":
                    target_id = data.get("target_id")
                    if target_id:
                        await db.mute_user(target_id)
                        await manager.send_to_user(target_id, {"type": "user_muted"})

                elif action == "mod_kick":
                    target_id = data.get("target_id")
                    if target_id:
                        await manager.send_to_user(target_id, {"type": "user_kicked"})
                        if target_id in manager.active_visitors:
                            await manager.active_visitors[target_id].close(code=1000)

                elif action == "mod_ban":
                    target_id = data.get("target_id")
                    if target_id:
                        await db.ban_user(target_id)
                        await manager.send_to_user(target_id, {"type": "user_banned"})
                        if target_id in manager.active_visitors:
                            await manager.active_visitors[target_id].close(code=1008)

        except WebSocketDisconnect:
            manager.disconnect_developer()
        return

    # Regular Visitor Connection
    # Check Ban Status
    if await db.is_banned(user_id):
        await websocket.accept()
        await websocket.send_json({"type": "user_banned"})
        await websocket.close(code=1008)
        return

    await manager.connect_visitor(user_id, websocket, name)
    
    # Send history
    history = await db.get_recent_messages(user_id=user_id)
    await websocket.send_json({"type": "history", "messages": history})

    # If muted, send notification
    if await db.is_muted(user_id):
        await websocket.send_json({"type": "user_muted"})

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "send_message":
                # Check mute & ban
                if await db.is_muted(user_id) or await db.is_banned(user_id):
                    await websocket.send_json({"type": "user_muted"})
                    continue

                msg_obj = {
                    "sender_id": user_id,
                    "sender_name": name,
                    "is_developer": False,
                    "msg_type": data.get("msg_type", "text"),
                    "content": data.get("content", ""),
                    "file_url": data.get("file_url")
                }
                await db.touch_user(user_id, name)
                await db.add_message(msg_obj)
                # Broadcast to sender & developer
                await websocket.send_json({"type": "chat", "message": msg_obj})
                await manager.send_to_dev({"type": "chat", "message": msg_obj})
                await manager.broadcast_users_to_dev()

            elif action == "call_request":
                if await db.is_muted(user_id) or await db.is_banned(user_id):
                    await websocket.send_json({"type": "user_muted"})
                    continue

                call_id = data.get("call_id")
                call_type = data.get("call_type", "voice")
                await db.create_call(call_id, user_id, name, call_type)

                # Send incoming call to developer console
                await manager.send_to_dev({
                    "type": "incoming_call",
                    "call_id": call_id,
                    "user_id": user_id,
                    "user_name": name,
                    "call_type": call_type
                })

                # Also alert developer via Telegram Bot
                asyncio.create_task(notify_admin_call_request(name, user_id, call_type, call_id))

            elif action == "webrtc_offer":
                # Forward caller's SDP Offer to developer
                call_id = data.get("call_id")
                await manager.send_to_dev({
                    "type": "webrtc_offer",
                    "from_id": user_id,
                    "call_id": call_id,
                    "sdp": data.get("sdp")
                })

            elif action == "webrtc_ice":
                # Forward caller's ICE candidate to developer
                await manager.send_to_dev({
                    "type": "webrtc_ice",
                    "from_id": user_id,
                    "candidate": data.get("candidate")
                })

            elif action == "call_end":
                call_id = data.get("call_id")
                await db.update_user_call_status(user_id, False)
                await manager.send_to_dev({"type": "call_ended", "call_id": call_id, "user_id": user_id})

    except WebSocketDisconnect:
        await manager.disconnect_visitor(user_id)
