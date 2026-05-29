<template>
  <!-- 未登录显示登录页 -->
  <Login v-if="!userId" @login="onLogin" />

  <div v-else class="layout">
    <header>
      <div class="status-dot" />
      <h1>Agent</h1>
      <span class="thread-id">{{ userId }} · {{ threadId }}</span>
      <button class="logout-btn" @click="logout">退出</button>
    </header>

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
import { ref, nextTick } from "vue";
import { marked } from "marked";
import type { Message, ToolCall } from "./types";
import FileUpload from "./components/FileUpload.vue";
import Login from "./components/Login.vue";

// 登录状态：userId 存在 sessionStorage，刷新不丢，关闭标签页清空
const userId = ref(sessionStorage.getItem("userId") ?? "");

function onLogin(name: string) {
  sessionStorage.setItem("userId", name);
  userId.value = name;
}

function logout() {
  sessionStorage.removeItem("userId");
  sessionStorage.removeItem("threadId");
  sessionStorage.removeItem("threadCreated");
  userId.value = "";
  messages.value = [];
  threadId.value = getOrCreateThreadId();
}

// 同一标签页内刷新保留对话，关闭标签页才是新对话
// LangGraph Server 要求 thread_id 必须是标准 UUID 格式
function getOrCreateThreadId() {
  const existing = sessionStorage.getItem("threadId");
  if (existing) return existing;
  // 生成标准 UUID v4（LangGraph Server 要求，不能用自定义字符串如 "web-abc123"）
  const id = crypto.randomUUID();
  sessionStorage.setItem("threadId", id);
  return id;
}
const threadId = ref(getOrCreateThreadId());

const messages = ref<Message[]>([]);
const inputText = ref("");
const loading = ref(false);
const messagesEl = ref<HTMLElement | null>(null);
const inputEl = ref<HTMLInputElement | null>(null);
const pendingFile = ref<{ file: File; docId: string } | null>(null);
const toast = ref({ visible: false, message: "", type: "success" });
let toastTimer: ReturnType<typeof setTimeout>;

function showToast(msg: string, type: "success" | "error" = "success") {
  clearTimeout(toastTimer);
  toast.value = { visible: true, message: msg, type };
  toastTimer = setTimeout(() => {
    toast.value.visible = false;
  }, 3000);
}

function onFileSelected(payload: { file: File; docId: string }) {
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
  return marked.parse(text) as string;
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

  // 显示用户消息（有文件时附加文件名）
  const displayText = file
    ? text
      ? `[📄 ${file.docId}]\n${text}`
      : `[📄 ${file.docId}]`
    : text;
  messages.value.push({ role: "user", content: displayText });
  messages.value.push({ role: "ai", content: "", streaming: true });
  scrollBottom();

  const aiMsg = messages.value[messages.value.length - 1];

  try {
    let chatMessage = text;

    // 如果有文件，先上传，拿到结果后注入到消息
    if (file) {
      const formData = new FormData();
      formData.append("file", file.file);
      formData.append("doc_id", file.docId);
      const uploadRes = await fetch("/upload", {
        method: "POST",
        body: formData,
      });
      const uploadText = await uploadRes.text();
      const uploadData = uploadText ? JSON.parse(uploadText) : {};
      const uploadResult =
        uploadData.message || (uploadRes.ok ? "文件上传成功" : "文件上传失败");
      if (!uploadRes.ok) showToast(uploadResult, "error");
      // 把文件解析结果注入消息，让 agent 告知用户
      chatMessage = text
        ? `${text}\n\n[文件已解析：${uploadResult}，请告知用户存储情况]`
        : `[文件已解析：${uploadResult}，请告知用户存储情况]`;
    }

    // ── 旧版：直接调自己的 FastAPI /chat 接口（纯文本流）──────────────────
    // const res = await fetch("/chat", {
    //   method: "POST",
    //   headers: { "Content-Type": "application/json" },
    //   body: JSON.stringify({
    //     message: chatMessage,
    //     thread_id: threadId.value,
    //     user_id: userId.value,
    //   }),
    // });
    // if (!res.ok) throw new Error(`HTTP ${res.status}`);
    // const reader = res.body!.getReader();
    // const decoder = new TextDecoder();
    // while (true) {
    //   const { done, value } = await reader.read();
    //   if (done) break;
    //   aiMsg.content += decoder.decode(value, { stream: true });
    //   scrollBottom();
    // }
    // ────────────────────────────────────────────────────────────────────────

    // ── 新版：调 LangGraph Server 标准接口（SSE JSON 事件流）───────────────
    // LangGraph Server 跑在 8123 端口
    // thread_id 放在 URL 路径里，user_id 放在 config.configurable 里

    // 确保 thread 已创建（LangGraph Server 要求先 POST /threads 创建，才能对其发 run）
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
      `/threads/${threadId.value}/runs/stream`, // 走 Vite 代理 → localhost:8123
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assistant_id: "agent",
          input: { messages: [{ role: "user", content: chatMessage }] },
          config: { configurable: { user_id: userId.value } },
          stream_mode: ["messages", "values"],
        }),
      }
    );

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    // LangGraph Server 返回 SSE 格式，每行是：data: {"event":"...","data":{...}}
    // event=messages/partial 且 data 有 content 时才是 AI 正在输出的文字
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      // 按行处理，SSE 每个事件以空行分隔
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith("data: ")) continue;
        // sse格式
        // event: values
        //   data: {"__interrupt__":[...]}

        //   event: messages/partial
        //   data: {"content":"你好"}

        //   event: messages/partial
        //   data: {"content":"你好，我是AI"}

        //   - event: — 事件类型（可选）
        //   - data: — 数据内容
        //   - 空行 — 表示一条消息结束
        // ── 处理 interrupt 事件（human review）──────────────────────────
        // interrupt 信息包含在 values 事件里，字段名是 __interrupt__
        //
        // LangGraph Server 返回的 values 事件数据结构：
        // {
        //   "messages": [...],           // 对话消息列表
        //   "__interrupt__": [           // 中断信息数组（仅当触发 interrupt() 时存在）
        //     {
        //       "value": {              // interrupt() 传入的参数（见 agent_graph.py 的 human_review 节点）
        //         "question": "AI 要执行以下操作，是否允许？",
        //         "tool_calls": [
        //           { "name": "save_user_info", "args": { "key": "name", "value": "张三" } },
        //           ...
        //         ]
        //       },
        //       "resumable": true,      // 是否可以恢复执行
        //       "ns": [...]             // 命名空间
        //     }
        //   ]
        // }
        if (currentEvent === "values") {
          try {
            const payload = JSON.parse(line.slice(6));
            const interrupts = payload?.__interrupt__;
            if (Array.isArray(interrupts) && interrupts.length > 0) {
              const interruptData = interrupts[0];
              const toolCalls: ToolCall[] =
                interruptData?.value?.tool_calls ?? [];

              // 结束 AI streaming 状态
              aiMsg.streaming = false;
              aiMsg.content = aiMsg.content || "我需要执行以下操作，请确认：";

              // 插入一条 review 消息，等用户点击
              messages.value.push({
                role: "review",
                content: interruptData?.value?.question ?? "是否允许执行？",
                toolCalls,
                reviewStatus: "pending",
              });
              scrollBottom();
            }
          } catch {
            // 解析失败忽略
          }
          continue;
        }

        // ── 处理 messages/partial 事件（正常流式输出）─────────────────────
        // 只处理 messages/partial 事件，其余（metadata、error 等）忽略
        if (currentEvent !== "messages/partial") continue;
        try {
          const payload = JSON.parse(line.slice(6));
          // messages/partial 的 payload 是 [msg]，msg.type==="ai" 才是模型输出
          const msg = Array.isArray(payload) ? payload[0] : null;
          if (
            msg?.type === "ai" &&
            msg?.content &&
            typeof msg.content === "string"
          ) {
            aiMsg.content = msg.content; // partial 是累积全文，直接赋值而不是追加
            scrollBottom();
          }
        } catch {
          // 非 JSON 行忽略
        }
      }
    }
    // ────────────────────────────────────────────────────────────────────────
  } catch (e: any) {
    aiMsg.content = `错误：${e.message}`;
  } finally {
    aiMsg.streaming = false;
    loading.value = false;
    scrollBottom();
    inputEl.value?.focus();
  }
}

// ── Human Review：用户点击同意/拒绝后恢复 graph 执行 ──────────────────────
async function handleReview(
  reviewMsg: Message,
  decision: "approve" | "reject"
) {
  reviewMsg.reviewStatus = decision === "approve" ? "approved" : "rejected";
  loading.value = true;

  // 添加一条 AI 消息用来接收恢复后的流式输出
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
        config: { configurable: { user_id: userId.value } },
        stream_mode: ["messages", "values"],
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      let currentEvent = "";
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
          continue;
        }
        if (!line.startsWith("data: ")) continue;
        if (currentEvent !== "messages/partial") continue;
        try {
          const payload = JSON.parse(line.slice(6));
          const msg = Array.isArray(payload) ? payload[0] : null;
          if (
            msg?.type === "ai" &&
            msg?.content &&
            typeof msg.content === "string"
          ) {
            aiMsg.content = msg.content;
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
