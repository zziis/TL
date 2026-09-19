/**
 * لوحة تحكم المطور (شبح) | GHOST DEVELOPER CORE ENGINE
 */

const urlParams = new URLSearchParams(window.location.search);
const secretKey = urlParams.get("secret") || "shabah_admin_secret";

let socket = null;
let currentCall = null;
let peerConnection = null;
let localStream = null;
let selectedUserId = null;
let pendingIceCandidates = [];
let allMessages = [];
const unreadByUser = {};
let isStealthMaskActive = false; // Mask active by default to protect developer identity

const iceServers = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" }
  ]
};

// UI Elements
const userListEl = document.getElementById("userList");
const userCountEl = document.getElementById("userCount");
const visitorVideo = document.getElementById("visitorVideo");
const devCallStatus = document.getElementById("devCallStatus");
const toggleMaskBtn = document.getElementById("toggleMaskBtn");
const devHangupBtn = document.getElementById("devHangupBtn");
const adminChatFeed = document.getElementById("adminChatFeed");
const devMsgInput = document.getElementById("devMsgInput");
const devSendBtn = document.getElementById("devSendBtn");

// Incoming Call Pop-up
const incomingCallAlert = document.getElementById("incomingCallAlert");
const callerNameSpan = document.getElementById("callerName");
const callTypeSpan = document.getElementById("callTypeSpan");
const btnAcceptCall = document.getElementById("btnAcceptCall");
const btnRejectCall = document.getElementById("btnRejectCall");

// Web Audio Ringtone Synth for incoming calls
function playRingBeep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(800, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.2);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) {}
}

function initAdminWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/shabah_dev?is_dev=true&secret=${encodeURIComponent(secretKey)}`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("⚡ Ghost Developer Console Connected");
    devCallStatus.textContent = "جاهز • في وضع التخفي (شبح)";
  };

  socket.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      handleAdminMessage(data);
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  socket.onclose = () => {
    devCallStatus.textContent = "انقطع الاتصال... جاري إعادة المحاولة";
    setTimeout(initAdminWebSocket, 3000);
  };
}

async function handleAdminMessage(data) {
  switch (data.type) {
    case "users_update":
      renderUserList(data.users);
      break;

    case "incoming_call":
      handleIncomingCall(data);
      break;

    case "webrtc_offer":
      handleCallerOffer(data);
      break;

    case "webrtc_ice":
      if (data.candidate) {
        if (peerConnection && peerConnection.remoteDescription) await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
        else pendingIceCandidates.push(data.candidate);
      }
      break;

    case "call_ended":
      terminateDevCall();
      break;

    case "chat":
      allMessages.push(data.message);
      if (!data.message.is_developer && String(data.message.sender_id) !== String(selectedUserId)) {
        unreadByUser[data.message.sender_id] = (unreadByUser[data.message.sender_id] || 0) + 1;
      }
      if (String(data.message.sender_id) === String(selectedUserId) || String(data.message.target_id || "") === String(selectedUserId)) renderSelectedChat();
      break;

    case "history":
      allMessages = data.messages || [];
      renderSelectedChat();
      break;
  }
}

// Render Online Visitors & Moderation Controls
function renderUserList(users) {
  userListEl.innerHTML = "";
  userCountEl.textContent = `${users.length} متصل`;

  if (users.length === 0) {
    userListEl.innerHTML = `<div style="text-align:center;color:#666;padding:20px;">لا يوجد زوار حالياً</div>`;
    return;
  }

  users.forEach(user => {
    if (user.id === "shabah_dev") return;

    const card = document.createElement("div");
    card.className = "user-card";
    card.onclick = () => selectUser(user.id, user.name || "زائر");

    card.innerHTML = `
      <div class="user-meta">
        <span class="user-name-title">${escapeHtml(user.name || "زائر")}</span>
        <span class="user-badge">${unreadByUser[user.id] ? `🔴 ${unreadByUser[user.id]} جديد` : (user.in_call ? "📞 في مكالمة" : "متصل")}</span>
      </div>
      <div style="font-size:11px;color:#889;margin-bottom:6px;">
        ID: <code>${user.id}</code> | انضم: ${user.joined_at?.split(" ")[1] || ""}
      </div>
      <div class="user-mod-actions">
        <button class="btn-mod mute" onclick="event.stopPropagation();muteUser('${user.id}')">كتم 🔇</button>
        <button class="btn-mod kick" onclick="event.stopPropagation();kickUser('${user.id}')">طرد ⚡</button>
        <button class="btn-mod ban" onclick="event.stopPropagation();banUser('${user.id}')">حظر 🚫</button>
      </div>
    `;

    userListEl.appendChild(card);
  });
}

// Moderation Actions (حظر، كتم، طرد)
window.muteUser = function(targetId) {
  if (confirm(`هل تريد كتم المستخدم ${targetId}؟`)) {
    socket.send(JSON.stringify({
      action: "mod_mute",
      target_id: targetId
    }));
  }
};

window.kickUser = function(targetId) {
  if (confirm(`هل تريد طرد المستخدم ${targetId} فوراً؟`)) {
    socket.send(JSON.stringify({
      action: "mod_kick",
      target_id: targetId
    }));
  }
};

window.banUser = function(targetId) {
  if (confirm(`هل تريد حظر المستخدم ${targetId} نهائياً؟`)) {
    socket.send(JSON.stringify({
      action: "mod_ban",
      target_id: targetId
    }));
  }
};

// Incoming Call Pop-up Handling
function handleIncomingCall(data) {
  currentCall = data;
  playRingBeep();
  callerNameSpan.textContent = data.user_name || "زائر";
  callTypeSpan.textContent = data.call_type === "voice" ? "🎙️ مايك (صوت)" : "📷 كاميرا وفيديو";
  incomingCallAlert.classList.add("active");
}

btnAcceptCall.onclick = async () => {
  incomingCallAlert.classList.remove("active");
  if (!currentCall) return;

  devCallStatus.textContent = `جاري الاتصال مع ${currentCall.user_name}...`;

  socket.send(JSON.stringify({
    action: "call_accept",
    call_id: currentCall.call_id,
    target_id: currentCall.user_id
  }));
};

btnRejectCall.onclick = () => {
  incomingCallAlert.classList.remove("active");
  if (!currentCall) return;

  socket.send(JSON.stringify({
    action: "call_reject",
    call_id: currentCall.call_id,
    target_id: currentCall.user_id
  }));
  currentCall = null;
};

// Handle Caller's WebRTC Offer
async function handleCallerOffer(data) {
  try {
    peerConnection = new RTCPeerConnection(iceServers);

    // Get developer microphone
    localStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: currentCall?.call_type === "video"
    });

    localStream.getTracks().forEach(track => {
      peerConnection.addTrack(track, localStream);
    });

    peerConnection.ontrack = (event) => {
      visitorVideo.srcObject = event.streams[0];
      devCallStatus.textContent = `⚡ متصل بمكالمة حية مع ${currentCall?.user_name || "المستخدم"}`;
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        socket.send(JSON.stringify({
          action: "webrtc_ice",
          target_id: data.from_id,
          candidate: event.candidate
        }));
      }
    };

    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
    for (const c of pendingIceCandidates.splice(0)) await peerConnection.addIceCandidate(new RTCIceCandidate(c));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);

    socket.send(JSON.stringify({
      action: "webrtc_answer",
      target_id: data.from_id,
      sdp: answer
    }));

    // Inform visitor about disguise mask
    socket.send(JSON.stringify({
      action: "toggle_mask",
      target_id: data.from_id,
      enabled: isStealthMaskActive
    }));

  } catch (err) {
    console.error("Dev WebRTC error:", err);
    alert("فشل بدء المكالمة من جهة المطور: " + err.message);
  }
}

// Developer Controls
toggleMaskBtn.onclick = () => {
  isStealthMaskActive = !isStealthMaskActive;
  toggleMaskBtn.classList.toggle("stealth-active", isStealthMaskActive);
  toggleMaskBtn.innerHTML = isStealthMaskActive 
    ? "💀 قناع شبح: مفعل (أنت مخفي)" 
    : "👤 قناع شبح: معطل (وجهك ظاهر)";

  if (socket && currentCall) {
    socket.send(JSON.stringify({
      action: "toggle_mask",
      target_id: currentCall.user_id,
      enabled: isStealthMaskActive
    }));
  }
};

devHangupBtn.onclick = () => {
  if (currentCall && socket) {
    socket.send(JSON.stringify({
      action: "call_end",
      call_id: currentCall.call_id,
      target_id: currentCall.user_id
    }));
  }
  terminateDevCall();
};

function terminateDevCall() {
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop());
    localStream = null;
  }
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  visitorVideo.srcObject = null;
  devCallStatus.textContent = "جاهز • في وضع التخفي (شبح)";
  currentCall = null;
}

// Chat Rendering & Sending as Developer
function renderAdminChatMessage(msg) {
  const isMe = msg.is_developer || msg.sender_id === "shabah_dev";
  const bubble = document.createElement("div");
  bubble.className = `message-bubble ${isMe ? 'outgoing' : 'incoming'}`;
  
  const senderTag = document.createElement("span");
  senderTag.className = "sender-tag";
  senderTag.textContent = isMe ? "💀 شبح (أنت)" : `${msg.sender_name} (${msg.sender_id})`;
  bubble.appendChild(senderTag);

  if (msg.msg_type === "text") {
    const textNode = document.createElement("div");
    textNode.textContent = msg.content;
    bubble.appendChild(textNode);
  } else if (msg.msg_type === "voice") {
    const audioWrap = document.createElement("div");
    audioWrap.className = "voice-message-player";
    const audio = new Audio(msg.file_url);
    const btn = document.createElement("button");
    btn.className = "btn-play-voice";
    btn.innerHTML = "▶";
    btn.onclick = () => {
      if (audio.paused) { audio.play(); btn.innerHTML = "⏸"; }
      else { audio.pause(); btn.innerHTML = "▶"; }
    };
    audio.onended = () => { btn.innerHTML = "▶"; };
    audioWrap.appendChild(btn);
    audioWrap.innerHTML += `<span style="font-size:11px;color:#00f3ff;margin-right:8px;">بصمة صوتية من المستخدم</span>`;
    bubble.appendChild(audioWrap);
  } else if (msg.msg_type === "image") {
    const img = document.createElement("img");
    img.src = msg.file_url;
    img.className = "image-message-view";
    img.onclick = () => window.open(msg.file_url, "_blank");
    bubble.appendChild(img);
  }

  const timeNode = document.createElement("span");
  timeNode.className = "msg-time";
  timeNode.textContent = msg.timestamp || "";
  bubble.appendChild(timeNode);

  adminChatFeed.appendChild(bubble);
  adminChatFeed.scrollTop = adminChatFeed.scrollHeight;
}

devSendBtn.onclick = sendDevMessage;
devMsgInput.onkeypress = (e) => {
  if (e.key === "Enter") sendDevMessage();
};

function sendDevMessage() {
  const text = devMsgInput.value.trim();
  if (!text || !socket) return;

  if (!selectedUserId) { alert("اختر مستخدماً من القائمة أولاً"); return; }
  socket.send(JSON.stringify({
    action: "send_message",
    target_id: selectedUserId,
    msg_type: "text",
    content: text
  }));

  devMsgInput.value = "";
}

function selectUser(id, name) {
  selectedUserId = String(id);
  unreadByUser[selectedUserId] = 0;
  devMsgInput.placeholder = `اكتب إلى ${name}...`;
  renderSelectedChat();
}

function renderSelectedChat() {
  adminChatFeed.innerHTML = "";
  if (!selectedUserId) {
    adminChatFeed.innerHTML = '<div style="text-align:center;color:#777;padding:30px">اختر مستخدماً من القائمة لفتح المحادثة الخاصة</div>';
    return;
  }
  allMessages.filter(m => String(m.sender_id) === selectedUserId || String(m.target_id || "") === selectedUserId)
    .forEach(m => renderAdminChatMessage(m));
  adminChatFeed.scrollTop = adminChatFeed.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

initAdminWebSocket();
