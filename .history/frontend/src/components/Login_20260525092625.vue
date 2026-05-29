<template>
  <div class="login-layout">
    <div class="login-box">
      <div class="login-title">你好</div>
      <div class="login-sub">输入用户名以开始</div>

      <form @submit.prevent="submit">
        <div class="field">
          <span class="field-prefix">›</span>
          <input
            ref="inputEl"
            v-model="username"
            class="field-input"
            placeholder="用户名"
            autocomplete="off"
            autofocus
          />
        </div>
        <button class="login-btn" :disabled="!username.trim()">进入 ↵</button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const emit = defineEmits<{ login: [userId: string] }>();

const username = ref("");
const inputEl = ref<HTMLInputElement | null>(null);

onMounted(() => inputEl.value?.focus());

function submit() {
  const name = username.value.trim();
  if (!name) return;
  emit("login", name);
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
