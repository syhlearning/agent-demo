<template>
  <!-- 未登录显示登录页 -->
  <Login v-if="!userId" @login="onLogin" />

  <div v-else class="layout">
    <header>
      <div class="status-dot" />
      <div class="company-logo">S</div>
      <h1>{{ ORG_NAME }}</h1>
      <span class="thread-id">{{ userLabel }} · {{ userId }} · {{ projectId }}</span>
      <button class="logout-btn" @click="logout">退出</button>
    </header>

    <div class="main-content">
      <!-- 左侧会话列表 -->
      <aside class="sidebar">
        <button class="new-chat-btn" @click="newConversation">+ 新对话</button>
        <div class="scope-panel">
          <div class="company-card">
            <div class="company-card-logo">S</div>
            <div>
              <div class="company-card-name">{{ ORG_NAME }}</div>
              <div class="company-card-id">{{ ORG_ID }}</div>
            </div>
          </div>
          <label>
            <span>项目</span>
            <input v-model="projectId" @change="saveScope" />
          </label>
          <button class="new-project-btn" @click="newProject">新页面项目</button>
        </div>
        <div class="conversation-list">
          <div
            v-for="conv in conversations"
            :key="conv.threadId"
            class="conv-item"
            :class="{ active: conv.threadId === threadId }"
            @click="switchConversation(conv.threadId)"
          >
            <div class="conv-title">{{ conv.title }}</div>
            <div class="conv-time">{{ formatTime(conv.createdAt) }}</div>
          </div>
          <div v-if="conversations.length === 0" class="conv-empty">暂无对话</div>
        </div>
      </aside>

      <!-- 中间聊天区 -->
      <div class="chat-area">
        <div
          ref="messagesEl"
          class="messages"
          :class="{ empty: messages.length === 0 }"
        >
          <!-- 空状态 -->
          <div v-if="messages.length === 0" class="empty-state">
            <div class="big">_</div>
            <div class="hint">输入消息开始对话</div>
          </div>

          <!-- 消息列表 -->
          <div v-for="(msg, i) in messages" :key="i" class="msg" :class="msg.role">
            <div class="label">
              {{
                msg.role === "user"
                  ? "you"
                  : msg.role === "review"
                  ? "review"
                  : "agent"
              }}
            </div>

            <!-- 人工审核消息 -->
            <div v-if="msg.role === 'review'" class="body review-body">
              <div class="review-question">{{ msg.content }}</div>
              <div v-if="msg.toolCalls?.length" class="review-tools">
                <div
                  v-for="(tc, j) in msg.toolCalls"
                  :key="j"
                  class="tool-call-item"
                >
                  <span class="tool-name">🔧 {{ tc.name }}</span>
                  <pre class="tool-args">{{
                    JSON.stringify(tc.args, null, 2)
                  }}</pre>
                </div>
              </div>
              <div v-if="msg.reviewStatus === 'pending'" class="review-actions">
                <button class="btn-approve" @click="handleReview(msg, 'approve')">
                  ✓ 允许
                </button>
                <button class="btn-reject" @click="handleReview(msg, 'reject')">
                  ✕ 拒绝
                </button>
              </div>
              <div v-else class="review-result" :class="msg.reviewStatus">
                {{ msg.reviewStatus === "approved" ? "✓ 已允许" : "✕ 已拒绝" }}
              </div>
            </div>

            <!-- AI 消息 -->
            <div
              v-else-if="msg.role === 'ai'"
              class="body"
              v-html="
                msg.streaming
                  ? escapeHtml(msg.content) + '<span class=\'cursor\'></span>'
                  : renderMarkdown(msg.content)
              "
            />
            <div v-else class="body">{{ msg.content }}</div>
          </div>
        </div>

        <div class="input-area">
          <!-- 文件 chip -->
          <Transition name="chip-slide">
            <div v-if="pendingFile" class="file-chip-bar">
              <div class="file-chip">
                <span class="chip-icon">📄</span>
                <span class="chip-name">{{ pendingFile.docId }}</span>
                <span class="chip-type">{{ pendingFile.docType }}</span>
                <button class="chip-remove" @click="pendingFile = null">✕</button>
              </div>
            </div>
          </Transition>

          <div class="input-inner">
            <FileUpload @file-selected="onFileSelected" />
            <span class="prompt">›</span>
            <input
              ref="inputEl"
              v-model="inputText"
              type="text"
              :placeholder="
                pendingFile ? '描述文件内容或直接发送…' : '有什么可以帮你的？'
              "
              :disabled="loading"
              autofocus
              @keydown.enter.exact.prevent="send"
            />
            <button :disabled="loading" @click="send">Enter ↵</button>
          </div>
        </div>
      </div>

      <!-- 右侧预览面板 -->
      <div v-if="previewUrl" class="preview-panel">
        <div class="preview-toolbar">
          <span class="preview-title">预览</span>
          <div class="preview-actions">
            <button
              class="preview-btn"
              :class="{ active: previewMode === 'pc' }"
              @click="previewMode = 'pc'"
            >PC</button>
            <button
              class="preview-btn"
              :class="{ active: previewMode === 'mobile' }"
              @click="previewMode = 'mobile'"
            >Mobile</button>
            <button class="preview-btn" @click="openInBrowser">🔗 打开</button>
            <button class="preview-btn close-btn" @click="previewUrl = null">✕</button>
          </div>
        </div>
        <div class="preview-frame-wrapper">
          <iframe
            :src="previewUrl"
            :style="{ width: previewMode === 'mobile' ? '375px' : '100%' }"
            class="preview-iframe"
            sandbox="allow-scripts allow-same-origin"
          />
        </div>
      </div>
    </div>

    <!-- Toast -->
    <Teleport to="body">
      <Transition name="toast-slide">
        <div v-if="toast.visible" class="toast" :class="toast.type">
          {{ toast.message }}
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import { marked } from "marked";
import type { Message, ToolCall, Conversation } from "./types";
import FileUpload from "./components/FileUpload.vue";
import Login from "./components/Login.vue";

// 登录状态
type UserIdentity = {
  userId: string;
  displayName: string;
};

const ORG_ID = "starlinke";
const ORG_NAME = "starlinke";
const DEFAULT_BRAND_ID = "default-brand";
const SAFE_SEGMENT_RE = /^[0-9A-Za-z._-]+$/;

function stableHash(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let value = 0x811c9dc5;
  for (const byte of bytes) {
    value ^= byte;
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value.toString(16).padStart(8, "0");
}

function segmentPrefix(defaultValue: string): string {
  let clean = (defaultValue || "item")
    .replace(/[^0-9A-Za-z]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
  if (clean.startsWith("default-")) clean = clean.slice("default-".length);
  return clean || "item";
}

function safeIdSegment(value: string, defaultValue = "user"): string {
  const raw = (value || "").trim();
  if (!raw) return defaultValue;

  const text = raw.replace(/^[.-]+|[.-]+$/g, "");
  if (text && SAFE_SEGMENT_RE.test(text)) return text;

  return `${segmentPrefix(defaultValue)}-${stableHash(raw)}`;
}

function conversationStorageKey(id: string) {
  return `conversations:${id}`;
}

function migrateConversationStorage(oldId: string, newId: string) {
  if (!oldId || oldId === newId) return;
  const oldKey = conversationStorageKey(oldId);
  const newKey = conversationStorageKey(newId);
  const oldValue = localStorage.getItem(oldKey);
  if (oldValue && !localStorage.getItem(newKey)) {
    localStorage.setItem(newKey, oldValue);
  }
}

function identityFromName(name: string): UserIdentity {
  const displayName = name.trim();
  return {
    userId: safeIdSegment(displayName, "default-user"),
    displayName,
  };
}

function loadStoredIdentity(): UserIdentity {
  const storedId = sessionStorage.getItem("userId") ?? "";
  const storedDisplayName = sessionStorage.getItem("userDisplayName") ?? "";
  if (!storedId) return { userId: "", displayName: "" };

  const identity = storedDisplayName
    ? { userId: safeIdSegment(storedId, "default-user"), displayName: storedDisplayName }
    : identityFromName(storedId);

  migrateConversationStorage(storedId, identity.userId);
  sessionStorage.setItem("userId", identity.userId);
  sessionStorage.setItem("userDisplayName", identity.displayName);
  return identity;
}

const initialIdentity = loadStoredIdentity();
const userId = ref(initialIdentity.userId);
const userDisplayName = ref(initialIdentity.displayName);
const userLabel = computed(() => userDisplayName.value || userId.value);

function onLogin(name: string) {
  const identity = identityFromName(name);
  migrateConversationStorage(name, identity.userId);
  sessionStorage.setItem("userId", identity.userId);
  sessionStorage.setItem("userDisplayName", identity.displayName);
  userId.value = identity.userId;
  userDisplayName.value = identity.displayName;
  loadConversations();
}

function logout() {
  sessionStorage.removeItem("userId");
  sessionStorage.removeItem("userDisplayName");
  sessionStorage.removeItem("threadId");
  sessionStorage.removeItem("threadCreated");
  sessionStorage.removeItem("brandId");
  sessionStorage.removeItem("projectId");
  userId.value = "";
  messages.value = [];
  conversations.value = [];
  threadId.value = getOrCreateThreadId();
}

function getOrCreateThreadId() {
  const existing = sessionStorage.getItem("threadId");
  if (existing) return existing;
  const id = crypto.randomUUID();
  sessionStorage.setItem("threadId", id);
  return id;
}
const threadId = ref(getOrCreateThreadId());

function getOrCreateProjectId() {
  const existing = sessionStorage.getItem("projectId");
  if (existing) return existing;
  const id = crypto.randomUUID();
  sessionStorage.setItem("projectId", id);
  return id;
}

const brandId = ref(DEFAULT_BRAND_ID);
const projectId = ref(getOrCreateProjectId());

function saveScope() {
  const cleanBrand = DEFAULT_BRAND_ID;
  const cleanProject = projectId.value.trim() || getOrCreateProjectId();
  brandId.value = cleanBrand;
  projectId.value = cleanProject;
  sessionStorage.setItem("brandId", cleanBrand);
  sessionStorage.setItem("projectId", cleanProject);
}

function currentConfig() {
  saveScope();
  return {
    org_id: ORG_ID,
    org_name: ORG_NAME,
    user_id: userId.value,
    user_display_name: userDisplayName.value,
    thread_id: threadId.value,
    brand_id: brandId.value,
    project_id: projectId.value,
  };
}

function withScope(content: string) {
  return `当前公司ID：${ORG_ID}\n当前公司名称：${ORG_NAME}\n当前用户ID：${userId.value}\n当前用户显示名：${userLabel.value}\n当前品牌ID：${brandId.value}\n当前项目ID：${projectId.value}\n\n${content}`;
}

const messages = ref<Message[]>([]);
const inputText = ref("");
const loading = ref(false);
const messagesEl = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLInputElement | null>(null);
const pendingFile = ref<{ file: File; docId: string; docType: string } | null>(null);
const toast = ref({ visible: false, message: "", type: "success" });
let toastTimer: ReturnType<typeof setTimeout>;

// 预览面板
const previewUrl = ref<string | null>(null);
const previewMode = ref<"pc" | "mobile">("pc");

// 会话列表
const conversations = ref<Conversation[]>([]);
const CONV_STORAGE_KEY = () => conversationStorageKey(userId.value);

function loadConversations() {
  try {
    const raw = localStorage.getItem(CONV_STORAGE_KEY());
    conversations.value = raw ? JSON.parse(raw) : [];
  } catch {
    conversations.value = [];
  }
}

function saveConversations() {
  localStorage.setItem(CONV_STORAGE_KEY(), JSON.stringify(conversations.value));
}

function addConversation(text: string) {
  // 不重复添加
  if (conversations.value.some((c) => c.threadId === threadId.value)) return;
  conversations.value.unshift({
    threadId: threadId.value,
    brandId: brandId.value,
    projectId: projectId.value,
    title: text.slice(0, 20) || "新对话",
    createdAt: Date.now(),
  });
  saveConversations();
}

function newConversation() {
  const id = crypto.randomUUID();
  sessionStorage.setItem("threadId", id);
  sessionStorage.removeItem("threadCreated");
  threadId.value = id;
  messages.value = [];
  previewUrl.value = null;
}

function newProject() {
  projectId.value = crypto.randomUUID();
  saveScope();
  newConversation();
}

async function switchConversation(tid: string) {
  if (tid === threadId.value) return;
  const conv = conversations.value.find((item) => item.threadId === tid);
  brandId.value = DEFAULT_BRAND_ID;
  if (conv?.projectId) projectId.value = conv.projectId;
  saveScope();
  sessionStorage.setItem("threadId", tid);
  sessionStorage.setItem("threadCreated", "1"); // 已有的对话肯定已创建
  threadId.value = tid;
  messages.value = [];
  previewUrl.value = null;
  await loadThreadMessages(tid);
}

async function loadThreadMessages(tid: string) {
  try {
    const res = await fetch(`/threads/${tid}/state`);
    if (!res.ok) return;
    const state = await res.json();
    const msgs = state?.values?.messages;
    if (!Array.isArray(msgs)) return;
    for (const m of msgs) {
      if (m.type === "human" && m.content) {
        messages.value.push({ role: "user", content: m.content });
      } else if (m.type === "ai" && m.content && typeof m.content === "string") {
        // 跳过 JSON 格式的 supervisor 输出
        if (m.content.trim().startsWith("{")) continue;
        messages.value.push({ role: "ai", content: m.content });
        const pUrl = extractPreviewUrl(m.content);
        if (pUrl) previewUrl.value = pUrl;
      }
    }
    scrollBottom();
  } catch {
    // 加载失败忽略
  }
}

function formatTime(ts: number) {
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function openInBrowser() {
  if (previewUrl.value) window.open(previewUrl.value, "_blank");
}

onMounted(() => {
  loadConversations();
  // 如果已有会话，加载历史消息
  if (sessionStorage.getItem("threadCreated")) {
    loadThreadMessages(threadId.value);
  }
});

// 解析 AI 消息中的 [PREVIEW:...] 标记
function extractPreviewPath(text: string): string | null {
  const marker = text.match(/\[PREVIEW:(\/projects\/[^\]\s]+)\]/);
  if (marker) return marker[1];

  const jsonUrl = text.match(/"preview_url"\s*:\s*"(\/projects\/[^"]+)"/);
  if (jsonUrl) return jsonUrl[1];

  const directUrl = text.match(/(\/projects\/[^\s)"'<>]+index\.html)/);
  return directUrl ? directUrl[1] : null;
}

function extractPreviewUrl(text: string): string | null {
  const path = extractPreviewPath(text);
  return path ? path + "?t=" + Date.now() : null;
}

function previewPath(url: string): string {
  return url.split("?")[0];
}

function ensurePreviewLink(msg: Message, url: string) {
  const path = previewPath(url);
  if (msg.content.includes(`[PREVIEW:${path}]`)) return;
  const suffix = `\n\n[PREVIEW:${path}]`;
  msg.content = msg.content ? msg.content + suffix : suffix.trim();
}

function applyPreviewFromText(msg: Message, text: string): string | null {
  const pUrl = extractPreviewUrl(text);
  if (!pUrl) return null;
  previewUrl.value = pUrl;
  ensurePreviewLink(msg, pUrl);
  return pUrl;
}

function applyPreviewFromMessages(msg: Message, payload: any): string | null {
  const msgs = payload?.messages;
  if (!Array.isArray(msgs)) return null;
  let found: string | null = null;
  for (const item of msgs) {
    if (typeof item?.content !== "string") continue;
    found = applyPreviewFromText(msg, item.content) || found;
  }
  return found;
}

function showToast(msg: string, type: "success" | "error" = "success") {
  clearTimeout(toastTimer);
  toast.value = { visible: true, message: msg, type };
  toastTimer = setTimeout(() => {
    toast.value.visible = false;
  }, 3000);
}

function onFileSelected(payload: { file: File; docId: string; docType: string }) {
  pendingFile.value = payload;
}

marked.use({ breaks: true, gfm: true });

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdown(text: string): string {
  // 将 [PREVIEW:...] 标记渲染成可点击链接
  const cleaned = text.replace(
    /\[PREVIEW:(\/projects\/[^\]]+)\]/g,
    (_match, path) => `[预览链接](${path}?t=${Date.now()})`
  );
  return marked.parse(cleaned) as string;
}

function scrollBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    }
  });
}

async function send() {
  const text = inputText.value.trim();
  if ((!text && !pendingFile.value) || loading.value) return;

  inputText.value = "";
  loading.value = true;

  const file = pendingFile.value;
  pendingFile.value = null;

  const displayText = file
    ? text
      ? `[📄 ${file.docId}]\n${text}`
      : `[📄 ${file.docId}]`
    : text;
  messages.value.push({ role: "user", content: displayText });
  messages.value.push({ role: "ai", content: "", streaming: true });
  scrollBottom();

  // 第一次发消息时保存会话
  addConversation(text || (file?.docId ?? "新对话"));

  const aiMsg = messages.value[messages.value.length - 1];

  try {
    let chatMessage = text;

    if (file) {
      const formData = new FormData();
      formData.append("file", file.file);
      formData.append("doc_id", file.docId);
      formData.append("doc_type", file.docType);
      formData.append("org_id", ORG_ID);
      formData.append("user_id", userId.value);
      formData.append("brand_id", brandId.value);
      formData.append("project_id", projectId.value);
      const uploadRes = await fetch("/upload", {
        method: "POST",
        body: formData,
      });
      const uploadText = await uploadRes.text();
      const uploadData = uploadText ? JSON.parse(uploadText) : {};
      const uploadResult =
        uploadData.message || (uploadRes.ok ? "文件上传成功" : "文件上传失败");
      if (!uploadRes.ok) showToast(uploadResult, "error");
      chatMessage = text
        ? `${text}\n\n[文件已解析：${uploadResult}，请告知用户存储情况]`
        : `[文件已解析：${uploadResult}，请告知用户存储情况]`;
    }

    if (!sessionStorage.getItem("threadCreated")) {
      const createRes = await fetch(`/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId.value }),
      });
      if (!createRes.ok)
        throw new Error(`创建 thread 失败: HTTP ${createRes.status}`);
      sessionStorage.setItem("threadCreated", "1");
    }

    const res = await fetch(
      `/threads/${threadId.value}/runs/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assistant_id: "agent",
          input: { messages: [{ role: "user", content: withScope(chatMessage) }] },
          config: { configurable: currentConfig() },
          stream_mode: ["messages", "values"],
        }),
      }
    );

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let currentEvent = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      // ── 逐行解析 SSE 事件流 ──────────────────────────────────────────────
      // SSE 原始格式示例（每个事件由 event 行 + data 行 + 空行组成）：
      //
      //   event: metadata
      //   data: {"run_id":"xxx"}
      //                                    ← 空行，表示一个事件结束
      //   event: values
      //   data: {"messages":[...],"__interrupt__":[...]}
      //
      //   event: messages/partial
      //   data: [{"type":"ai","content":"你好","name":"researcher"}]
      //
      //   event: messages/partial
      //   data: [{"type":"ai","content":"你好！今天","name":"researcher"}]
      //
      //   event: end
      //   data: null
      //
      // lines 数组就是按 \n 拆分后的每一行
      for (const line of lines) {

        // ── 第 1 关：识别事件类型 ────────────────────────────────────────
        // 遇到 "event: xxx" 行 → 记住当前事件类型，等下一行 data 来了配合使用
        // 例如 "event: values" → currentEvent = "values"
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
          continue; // 这行本身没有数据，跳到下一行去读 data
        }

        // ── 第 2 关：跳过非 data 行 ─────────────────────────────────────
        // 空行、注释行等都不处理，只处理 "data: {...}" 格式的行
        if (!line.startsWith("data: ")) continue;

        // ── 第 3 关：处理 values 事件 ───────────────────────────────────
        // values 事件 = 某个节点执行完毕后的完整 state 快照
        // 数据结构：
        // {
        //   "messages": [                    // 完整消息历史
        //     {"type":"human","content":"你好"},
        //     {"type":"ai","content":"你好！有什么可以帮你的？"}
        //   ],
        //   "next": "researcher",            // 下一个要执行的节点（可选）
        //   "__interrupt__": [               // 中断信息（仅触发 interrupt() 时存在）
        //     {
        //       "value": {
        //         "question": "AI 要执行以下操作，是否允许？",
        //         "tool_calls": [{"name":"save_user_info","args":{...}}]
        //       },
        //       "resumable": true
        //     }
        //   ]
        // }
        //
        // 两种情况会用到 values 事件：
        // A. 有 __interrupt__ → 显示人工审核 UI
        // B. supervisor 选了 FINISH → 从 messages 数组最后一条拿到直接回复
        if (currentEvent === "values") {
          try {
            const payload = JSON.parse(line.slice(6));

            // ── A. 检查是否有人工审核中断 ──
            const interrupts = payload?.__interrupt__;
            if (Array.isArray(interrupts) && interrupts.length > 0) {
              const interruptData = interrupts[0];
              const toolCalls: ToolCall[] =
                interruptData?.value?.tool_calls ?? [];
              aiMsg.streaming = false;
              aiMsg.content = aiMsg.content || "我需要执行以下操作，请确认：";
              messages.value.push({
                role: "review",
                content: interruptData?.value?.question ?? "是否允许执行？",
                toolCalls,
                reviewStatus: "pending",
              });
              scrollBottom();
            }

            // ── B. 提取 supervisor FINISH 的回复 ──
            // supervisor 选 FINISH 时，supervisor_node 返回 AIMessage(content=response)
            // 这条消息会出现在 messages 数组的最后一条
            // 但 messages/partial 里只有 supervisor 的 JSON（被过滤了），所以要从这里拿
            const msgs = payload?.messages;
            if (Array.isArray(msgs) && msgs.length > 0) {
              const lastMsg = msgs[msgs.length - 1];
              if (
                lastMsg?.type === "ai" &&
                lastMsg?.content &&
                typeof lastMsg.content === "string" &&
                !lastMsg.content.trim().startsWith("{") // 排除 structured output JSON
              ) {
                aiMsg.content = lastMsg.content;
                scrollBottom();
              }
            }
            applyPreviewFromMessages(aiMsg, payload);
          } catch {
            // 解析失败忽略
          }
          continue; // values 处理完毕，跳到下一行
        }

        // ── 第 4 关：只处理 messages/partial 事件 ───────────────────────
        // 其他事件类型（metadata、messages/complete、end 等）不处理
        if (currentEvent !== "messages/partial") continue;

        try {
          // messages/partial 事件的数据格式（LangGraph Server 固定格式）：
          // data: [
          //   {
          //     "type": "ai",          // 消息类型："ai" | "human" | "tool"
          //     "content": "你好...",   // 累积的完整文本（不是增量，每次都是全文）
          //     "name": "supervisor",   // 产生该消息的节点名（可选，如 "supervisor"、"researcher"）
          //     "id": "xxx",           // 消息 ID
          //     "tool_calls": [...]    // 工具调用（如有）
          //   }
          // ]
          // 注意：payload 是数组，取 [0] 拿到消息对象
          const payload = JSON.parse(line.slice(6));
          const msg = Array.isArray(payload) ? payload[0] : null;
          if (
            msg?.type === "ai" &&
            msg?.content &&
            typeof msg.content === "string"
          ) {
            // 跳过 JSON 格式输出（supervisor 路由决策的 structured output）
            const trimmed = msg.content.trim();
            if (
              trimmed.startsWith("{") ||
              (trimmed.startsWith("[") && !trimmed.startsWith("[PREVIEW:"))
            )
              continue;
            aiMsg.content = msg.content;
            // 检测预览标记
            applyPreviewFromText(aiMsg, msg.content);
            scrollBottom();
          }
        } catch {
          // ignore
        }
      }
    }
  } catch (e: any) {
    aiMsg.content = `错误：${e.message}`;
  } finally {
    aiMsg.streaming = false;
    loading.value = false;
    scrollBottom();
    inputEl.value?.focus();
  }
}

async function handleReview(
  reviewMsg: Message,
  decision: "approve" | "reject"
) {
  reviewMsg.reviewStatus = decision === "approve" ? "approved" : "rejected";
  loading.value = true;

  messages.value.push({ role: "ai", content: "", streaming: true });
  const aiMsg = messages.value[messages.value.length - 1];
  scrollBottom();

  try {
    const res = await fetch(`/threads/${threadId.value}/runs/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assistant_id: "agent",
        command: { resume: decision },
        config: { configurable: currentConfig() },
        stream_mode: ["messages", "values"],
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let currentEvent = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith("data: ")) continue;

        // 从 values 事件中提取子 agent 的最终回复
        if (currentEvent === "values") {
          try {
            const payload = JSON.parse(line.slice(6));
            const msgs = payload?.messages;
            if (Array.isArray(msgs) && msgs.length > 0) {
              const lastMsg = msgs[msgs.length - 1];
              if (
                lastMsg?.type === "ai" &&
                lastMsg?.content &&
                typeof lastMsg.content === "string" &&
                !lastMsg.content.trim().startsWith("{")
              ) {
                aiMsg.content = lastMsg.content;
                scrollBottom();
              }
            }
            applyPreviewFromMessages(aiMsg, payload);
          } catch {
            // ignore
          }
          continue;
        }

        if (currentEvent !== "messages/partial") continue;
        try {
          const payload = JSON.parse(line.slice(6));
          const msg = Array.isArray(payload) ? payload[0] : null;
          if (
            msg?.type === "ai" &&
            msg?.content &&
            typeof msg.content === "string"
          ) {
            // 跳过 JSON 格式输出（supervisor 路由决策的 structured output）
            const trimmed = msg.content.trim();
            if (
              trimmed.startsWith("{") ||
              (trimmed.startsWith("[") && !trimmed.startsWith("[PREVIEW:"))
            )
              continue;
            aiMsg.content = msg.content;
            applyPreviewFromText(aiMsg, msg.content);
            scrollBottom();
          }
        } catch {
          // ignore
        }
      }
    }
  } catch (e: any) {
    aiMsg.content = `错误：${e.message}`;
  } finally {
    aiMsg.streaming = false;
    loading.value = false;
    scrollBottom();
    inputEl.value?.focus();
  }
}
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background: #0d0d0d;
  color: #e0e0e0;
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", ui-monospace,
    monospace;
  font-size: 14px;
  line-height: 1.6;
  height: 100vh;
  overflow: hidden;
}

.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* ── Header ── */
header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border-bottom: 1px solid #1e1e1e;
}
.status-dot {
  width: 7px;
  height: 7px;
  background: #3fb950;
  border-radius: 50%;
}
header h1 {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 0.05em;
}
.company-logo,
.company-card-logo {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: 1px solid #384152;
  border-radius: 6px;
  background: #121820;
  color: #c7d2fe;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
}
.thread-id {
  margin-left: auto;
  font-size: 11px;
  color: #404040;
}
.logout-btn {
  background: none;
  border: 1px solid #252525;
  color: #404040;
  padding: 3px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  transition: border-color 0.15s, color 0.15s;
}
.logout-btn:hover {
  border-color: #f87171;
  color: #f87171;
}

/* ── Main Content (3 columns) ── */
.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #1e1e1e;
  display: flex;
  flex-direction: column;
  background: #0a0a0a;
}
.new-chat-btn {
  margin: 12px;
  padding: 8px;
  background: #111;
  border: 1px solid #252525;
  color: #888;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  transition: border-color 0.15s, color 0.15s;
}
.new-chat-btn:hover {
  border-color: #6e5fdb;
  color: #6e5fdb;
}
.scope-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 12px 12px;
  border-bottom: 1px solid #171717;
}
.company-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid #1f2937;
  border-radius: 6px;
  background: #0d1117;
}
.company-card-logo {
  width: 28px;
  height: 28px;
  border-color: #46556f;
  font-size: 14px;
}
.company-card-name {
  color: #e5e7eb;
  font-size: 12px;
  font-weight: 700;
}
.company-card-id {
  margin-top: 2px;
  color: #64748b;
  font-size: 10px;
}
.scope-panel label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 10px;
  color: #444;
}
.scope-panel input {
  width: 100%;
  background: #0d0d0d;
  border: 1px solid #222;
  border-radius: 5px;
  color: #aaa;
  font-family: inherit;
  font-size: 11px;
  padding: 6px 8px;
  outline: none;
}
.scope-panel input:focus {
  border-color: #6e5fdb;
}
.new-project-btn {
  background: transparent;
  border: 1px solid #252525;
  color: #555;
  padding: 6px;
  border-radius: 5px;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  transition: border-color 0.15s, color 0.15s;
}
.new-project-btn:hover {
  border-color: #6e5fdb;
  color: #6e5fdb;
}
.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.conversation-list::-webkit-scrollbar {
  width: 3px;
}
.conversation-list::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}
.conv-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
}
.conv-item:hover {
  background: #1a1a1a;
}
.conv-item.active {
  background: #1a1a2e;
  border: 1px solid #2a2a4e;
}
.conv-title {
  font-size: 12px;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.conv-time {
  font-size: 10px;
  color: #444;
  margin-top: 2px;
}
.conv-empty {
  text-align: center;
  color: #333;
  font-size: 12px;
  padding: 24px 0;
}

/* ── Chat Area ── */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* ── Messages ── */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}
.messages.empty {
  justify-content: center;
}
.messages::-webkit-scrollbar {
  width: 3px;
}
.messages::-webkit-scrollbar-track {
  background: transparent;
}
.messages::-webkit-scrollbar-thumb {
  background: #2a2a2a;
  border-radius: 2px;
}

.msg {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 820px;
  width: 100%;
}
.msg.user .label {
  color: #6e5fdb;
  font-size: 12px;
}
.msg.user .body {
  color: #888;
  padding-left: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.ai .label {
  color: #3fb950;
  font-size: 12px;
}
.msg.ai .body {
  color: #dde1e7;
}

/* markdown */
.msg.ai .body p {
  margin: 4px 0;
}
.msg.ai .body h1,
.msg.ai .body h2,
.msg.ai .body h3 {
  color: #fff;
  margin: 14px 0 6px;
}
.msg.ai .body ul,
.msg.ai .body ol {
  padding-left: 22px;
  margin: 6px 0;
}
.msg.ai .body li {
  margin: 2px 0;
}
.msg.ai .body a {
  color: #7c9ef8;
  text-decoration: none;
}
.msg.ai .body a:hover {
  text-decoration: underline;
}
.msg.ai .body blockquote {
  border-left: 3px solid #2d2d2d;
  padding-left: 12px;
  color: #888;
  margin: 6px 0;
}
.msg.ai .body code {
  background: #1a1a1a;
  border: 1px solid #252525;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
  color: #7dd3fc;
}
.msg.ai .body pre {
  background: #111;
  border: 1px solid #222;
  border-radius: 6px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 10px 0;
}
.msg.ai .body pre code {
  background: none;
  border: none;
  padding: 0;
  color: #e0e0e0;
  font-size: 13px;
}
.msg.ai .body table {
  border-collapse: collapse;
  margin: 10px 0;
  width: 100%;
  font-size: 13px;
}
.msg.ai .body th,
.msg.ai .body td {
  border: 1px solid #222;
  padding: 6px 12px;
  text-align: left;
}
.msg.ai .body th {
  background: #141414;
  color: #aaa;
}
.msg.ai .body hr {
  border: none;
  border-top: 1px solid #1e1e1e;
  margin: 12px 0;
}

/* streaming cursor */
.cursor {
  display: inline-block;
  width: 7px;
  height: 13px;
  background: #6e5fdb;
  border-radius: 1px;
  vertical-align: text-bottom;
  animation: blink 0.9s step-end infinite;
}
@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

/* ── Input area ── */
.input-area {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 24px 24px;
  border-top: 1px solid #1a1a1a;
  background: #0d0d0d;
  gap: 6px;
}
.input-inner {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 720px;
  background: #111;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 10px 16px;
}
.prompt {
  color: #6e5fdb;
  font-size: 15px;
  user-select: none;
}
.input-inner input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 14px;
  caret-color: #6e5fdb;
}
.input-inner input::placeholder {
  color: #333;
}
.input-inner input:disabled {
  opacity: 0.4;
}
.input-inner button {
  background: none;
  border: 1px solid #252525;
  color: #505050;
  padding: 4px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  transition: border-color 0.15s, color 0.15s;
  white-space: nowrap;
}
.input-inner button:hover:not(:disabled) {
  border-color: #6e5fdb;
  color: #6e5fdb;
}
.input-inner button:disabled {
  opacity: 0.3;
  cursor: default;
}

/* ── 文件 chip ── */
.file-chip-bar {
  width: 100%;
  max-width: 720px;
}
.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: #111;
  border: 1px solid #6e5fdb;
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  color: #a89ee8;
}
.chip-icon {
  font-size: 13px;
}
.chip-name {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip-type {
  color: #6e5fdb;
  font-size: 10px;
  border: 1px solid #2a2550;
  border-radius: 4px;
  padding: 1px 5px;
}
.chip-remove {
  background: none;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  line-height: 1;
  transition: color 0.15s;
}
.chip-remove:hover {
  color: #f87171;
}

.chip-slide-enter-active,
.chip-slide-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.chip-slide-enter-from,
.chip-slide-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* ── Preview Panel ── */
.preview-panel {
  width: 50%;
  flex-shrink: 0;
  border-left: 1px solid #1e1e1e;
  display: flex;
  flex-direction: column;
  background: #0a0a0a;
}
.preview-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #1e1e1e;
  background: #111;
}
.preview-title {
  font-size: 12px;
  color: #888;
  font-weight: 600;
}
.preview-actions {
  display: flex;
  gap: 6px;
}
.preview-btn {
  background: none;
  border: 1px solid #252525;
  color: #666;
  padding: 3px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 11px;
  transition: border-color 0.15s, color 0.15s;
}
.preview-btn:hover {
  border-color: #6e5fdb;
  color: #6e5fdb;
}
.preview-btn.active {
  border-color: #6e5fdb;
  color: #6e5fdb;
  background: #1a1a2e;
}
.preview-btn.close-btn:hover {
  border-color: #f87171;
  color: #f87171;
}
.preview-frame-wrapper {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  overflow: auto;
  padding: 12px;
  background: #1a1a1a;
}
.preview-iframe {
  height: 100%;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  background: #fff;
}

/* ── Toast ── */
.toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: #111;
  border: 1px solid #1e1e1e;
  color: #dde1e7;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 12px;
  padding: 10px 20px;
  border-radius: 6px;
  z-index: 9998;
  white-space: nowrap;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
}
.toast.success {
  border-color: #3fb950;
  color: #3fb950;
}
.toast.error {
  border-color: #f87171;
  color: #f87171;
}
.toast-slide-enter-active,
.toast-slide-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.toast-slide-enter-from,
.toast-slide-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}

/* ── Human Review ── */
.msg.review .label {
  color: #f59e0b;
  font-size: 12px;
}
.review-body {
  background: #1a1700;
  border: 1px solid #3d3200;
  border-radius: 8px;
  padding: 14px 16px;
}
.review-question {
  color: #f59e0b;
  font-size: 13px;
  margin-bottom: 10px;
}
.review-tools {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.tool-call-item {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 10px 12px;
}
.tool-name {
  color: #7dd3fc;
  font-size: 13px;
  font-weight: 600;
}
.tool-args {
  color: #888;
  font-size: 12px;
  margin: 6px 0 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.review-actions {
  display: flex;
  gap: 10px;
}
.btn-approve,
.btn-reject {
  padding: 6px 18px;
  border-radius: 5px;
  border: 1px solid;
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-approve {
  background: #0d2818;
  border-color: #3fb950;
  color: #3fb950;
}
.btn-approve:hover {
  opacity: 0.8;
}
.btn-reject {
  background: #2d1215;
  border-color: #f87171;
  color: #f87171;
}
.btn-reject:hover {
  opacity: 0.8;
}
.review-result {
  font-size: 13px;
  font-weight: 600;
}
.review-result.approved {
  color: #3fb950;
}
.review-result.rejected {
  color: #f87171;
}

/* empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: #2a2a2a;
  pointer-events: none;
  user-select: none;
}
.empty-state .big {
  font-size: 32px;
}
.empty-state .hint {
  font-size: 12px;
}
</style>
