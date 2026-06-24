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

        <button class="login-btn" :disabled="!canSubmit || loading">
          {{ loading ? "处理中..." : mode === "login" ? "登录 ↵" : "注册并进入 ↵" }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from "vue";

type AuthMode = "login" | "register";

type AuthResponse = {
  access_token: string;
  refresh_token: string;
  user: {
    username: string;
  };
};

type LoginPayload = {
  userId: string;
  displayName: string;
  accessToken: string;
  refreshToken: string;
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

const canSubmit = computed(() => {
  const nameOk = username.value.trim().length >= 3;
  const passwordOk = mode.value === "login"
    ? password.value.length > 0
    : password.value.length >= 8;
  return nameOk && passwordOk;
});

async function submit() {
  if (!canSubmit.value || loading.value) return;

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
    const data = await response.json().catch(() => null);

    if (!response.ok) {
      error.value = data?.detail || "认证失败";
      return;
    }

    const auth = data as AuthResponse;
    emit("login", {
      userId: auth.user.username,
      displayName: auth.user.username,
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token,
    });
  } catch (err) {
    error.value = err instanceof Error ? err.message : "网络错误";
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
