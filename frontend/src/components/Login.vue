<template>
  <div class="login-layout">
    <div class="login-box">
      <div class="login-title">你好</div>
      <div class="login-sub">登录后开始</div>

      <form @submit.prevent="submit">
        <div class="mode-tabs" aria-label="认证模式">
          <button
            type="button"
            :class="{ active: mode === 'login' }"
            @click="mode = 'login'"
          >
            登录
          </button>
          <button
            type="button"
            :class="{ active: mode === 'register' }"
            @click="mode = 'register'"
          >
            注册
          </button>
        </div>

        <div class="field">
          <span class="field-prefix">›</span>
          <input
            ref="inputEl"
            v-model="username"
            class="field-input"
            placeholder="用户名"
            autocomplete="username"
            autofocus
          />
        </div>

        <div v-if="mode === 'register'" class="field">
          <span class="field-prefix">@</span>
          <input
            v-model="email"
            class="field-input"
            placeholder="邮箱（可选）"
            autocomplete="email"
          />
        </div>

        <div class="field">
          <span class="field-prefix">*</span>
          <input
            v-model="password"
            class="field-input"
            placeholder="密码"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          />
        </div>

        <div v-if="error" class="login-error">{{ error }}</div>

        <button class="login-btn" :disabled="loading">
          {{ loading ? "处理中..." : mode === "login" ? "登录 ↵" : "注册并进入 ↵" }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

type AuthMode = "login" | "register";

type AuthResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
  user: {
    username: string;
  };
};

type LoginPayload = {
  userId: string;
  displayName: string;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  refreshExpiresIn: number;
};

type ValidationIssue = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
};

type ErrorResponse = {
  detail?: string | ValidationIssue[];
  message?: string;
};

const emit = defineEmits<{ login: [payload: LoginPayload] }>();

const username = ref("");
const password = ref("");
const email = ref("");
const mode = ref<AuthMode>("login");
const loading = ref(false);
const error = ref("");
const inputEl = ref<HTMLInputElement | null>(null);

onMounted(() => inputEl.value?.focus());

const usernamePattern = /^[0-9A-Za-z._-]+$/;
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateForm(): string {
  const name = username.value.trim();
  const mail = email.value.trim();

  if (!name) return "请输入用户名";
  if (!password.value) return "请输入密码";

  if (mode.value === "register") {
    if (name.length < 3) return "用户名至少 3 个字符";
    if (!usernamePattern.test(name)) return "用户名只能包含英文、数字、点、下划线和短横线";
    if (password.value.length < 8) return "密码至少 8 位";
    if (mail && !emailPattern.test(mail)) return "请输入正确的邮箱地址";
  }

  return "";
}

function messageFromIssue(issue: ValidationIssue): string {
  const field = String(issue.loc?.at(-1) ?? "");
  const type = issue.type ?? "";

  if (field === "username") {
    if (type.includes("string_too_short")) return "用户名至少 3 个字符";
    if (type.includes("string_too_long")) return "用户名不能超过 64 个字符";
    if (type.includes("string_pattern_mismatch")) return "用户名只能包含英文、数字、点、下划线和短横线";
    return "请输入正确的用户名";
  }

  if (field === "password") {
    if (type.includes("string_too_short")) return "密码至少 8 位";
    if (type.includes("string_too_long")) return "密码不能超过 128 位";
    return "请输入正确的密码";
  }

  if (field === "email") return "请输入正确的邮箱地址";
  return issue.msg || "提交失败，请检查输入信息";
}

function friendlyAuthError(data: ErrorResponse | null, status: number): string {
  const detail = data?.detail ?? data?.message;

  if (typeof detail === "string") {
    const messages: Record<string, string> = {
      "Username or email already exists": "用户名或邮箱已存在",
      "Incorrect username or password": "用户名或密码错误",
      "Inactive user": "账号已被禁用",
    };
    return messages[detail] || detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return messageFromIssue(detail[0]);
  }

  if (status === 409) return "用户名或邮箱已存在";
  if (status === 401) return "用户名或密码错误";
  if (status === 422) return "提交失败，请检查输入信息";
  if ([502, 503, 504].includes(status)) return "认证服务暂时不可用，请确认后端服务正在运行";
  if (status >= 500) return "认证服务内部错误，请查看后端日志";
  return `认证请求失败（HTTP ${status}）`;
}

async function readAuthResponse(response: Response): Promise<AuthResponse | ErrorResponse | null> {
  const text = await response.text();
  if (!text) return null;

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return { message: text.slice(0, 200) };
  }

  try {
    return JSON.parse(text) as AuthResponse | ErrorResponse;
  } catch {
    return { message: "认证服务返回了无法解析的响应" };
  }
}

function friendlyNetworkError(err: unknown): string {
  if (err instanceof TypeError) {
    return "无法连接认证服务，请确认 FastAPI 后端已在 8000 端口正常运行";
  }

  if (err instanceof Error) {
    const message = err.message.toLowerCase();
    if (message.includes("socket hang up") || message.includes("failed to fetch")) {
      return "认证服务连接被断开，请重启 8000 端口上的后端服务";
    }
    return err.message;
  }

  return "网络错误，请确认后端服务是否正常运行";
}

async function submit() {
  if (loading.value) return;

  const validationMessage = validateForm();
  if (validationMessage) {
    error.value = validationMessage;
    return;
  }

  loading.value = true;
  error.value = "";

  try {
    const body: Record<string, string> = {
      username: username.value.trim(),
      password: password.value,
    };
    if (mode.value === "register" && email.value.trim()) {
      body.email = email.value.trim();
    }

    const response = await fetch(`/auth/${mode.value}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await readAuthResponse(response);

    if (!response.ok) {
      error.value = friendlyAuthError(data as ErrorResponse | null, response.status);
      return;
    }

    const auth = data as AuthResponse;
    emit("login", {
      userId: auth.user.username,
      displayName: auth.user.username,
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token,
      expiresIn: auth.expires_in,
      refreshExpiresIn: auth.refresh_expires_in,
    });
  } catch (err) {
    error.value = friendlyNetworkError(err);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-layout {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0d0d0d;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}

.login-box {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 320px;
}

.login-title {
  font-size: 20px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 0.05em;
}

.login-sub {
  font-size: 12px;
  color: #333;
  margin-top: -16px;
}

form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 2px;
}

.mode-tabs button {
  background: transparent;
  border: 1px solid #222;
  color: #555;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
}

.mode-tabs button.active {
  border-color: #6e5fdb;
  color: #d8d4ff;
}

.field {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #111;
  border: 1px solid #222;
  border-radius: 8px;
  padding: 10px 16px;
}

.field-prefix {
  color: #6e5fdb;
  font-size: 15px;
  user-select: none;
}

.field-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 14px;
  caret-color: #6e5fdb;
}
.field-input::placeholder {
  color: #333;
}

.login-error {
  color: #d87272;
  font-size: 12px;
  line-height: 1.5;
}

.login-btn {
  width: 100%;
  background: transparent;
  border: 1px solid #2a2a2a;
  color: #555;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  transition: border-color 0.15s, color 0.15s;
}
.login-btn:hover:not(:disabled) {
  border-color: #6e5fdb;
  color: #6e5fdb;
}
.login-btn:disabled {
  opacity: 0.3;
  cursor: default;
}
</style>
