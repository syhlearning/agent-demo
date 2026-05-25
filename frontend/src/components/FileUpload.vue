<template>
  <!-- "+" 触发按钮 -->
  <button class="upload-btn" title="上传文件" @click="dialogVisible = true">+</button>

  <Teleport to="body">
    <!-- 选文件 modal -->
    <Transition name="fade">
      <div v-if="dialogVisible" class="overlay" @click.self="close">
        <div class="modal">
          <div class="modal-header">
            <span class="modal-title">选择文件</span>
            <button class="close-btn" @click="close">✕</button>
          </div>

          <!-- 拖拽区域 -->
          <div
            class="drop-zone"
            :class="{ 'drop-zone--over': isOver, 'drop-zone--has-file': !!selectedFile }"
            @dragover.prevent="isOver = true"
            @dragleave="isOver = false"
            @drop.prevent="onZoneDrop"
            @click="fileInput?.click()"
          >
            <input ref="fileInput" type="file" accept=".pdf,.doc,.docx,.txt,.md" style="display:none" @change="onInputChange" />
            <template v-if="selectedFile">
              <span class="file-icon">📄</span>
              <span class="file-name">{{ selectedFile.name }}</span>
              <span class="file-size">{{ formatSize(selectedFile.size) }}</span>
            </template>
            <template v-else>
              <span class="drop-icon">↑</span>
              <span class="drop-text">拖拽文件到此处，或 <em>点击选择</em></span>
              <span class="drop-hint">PDF · Word · TXT · Markdown</span>
            </template>
          </div>

          <!-- 文档 ID -->
          <div class="field-row">
            <label class="field-label">文档 ID</label>
            <input v-model="docId" class="field-input" placeholder="留空则用文件名" />
          </div>

          <div class="modal-footer">
            <button class="btn" @click="close">取消</button>
            <button class="btn btn--primary" :disabled="!selectedFile" @click="confirm">确认</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 全屏拖拽遮罩 -->
    <Transition name="fade">
      <div v-if="isDraggingOver" class="drag-overlay" @dragover.prevent @drop.prevent="onWindowDrop">
        <div class="drag-hint">
          <span style="font-size:40px">↑</span>
          <span>松开以上传文件</span>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const emit = defineEmits<{
  'file-selected': [payload: { file: File; docId: string }]
}>()

const dialogVisible = ref(false)
const selectedFile = ref<File | null>(null)
const docId = ref('')
const isOver = ref(false)
const isDraggingOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
let dragCounter = 0

function close() {
  dialogVisible.value = false
  selectedFile.value = null
  docId.value = ''
}

function confirm() {
  if (!selectedFile.value) return
  emit('file-selected', {
    file: selectedFile.value,
    docId: docId.value || selectedFile.value.name.replace(/\.[^.]+$/, ''),
  })
  close()
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? (bytes / 1024).toFixed(1) + ' KB'
    : (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function pickFile(file: File) {
  selectedFile.value = file
  if (!docId.value) docId.value = file.name.replace(/\.[^.]+$/, '')
}

function onInputChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) pickFile(file)
}

function onZoneDrop(e: DragEvent) {
  isOver.value = false
  const file = e.dataTransfer?.files[0]
  if (file) pickFile(file)
}

function onDragEnter(e: DragEvent) {
  if (!e.dataTransfer?.types.includes('Files')) return
  dragCounter++
  isDraggingOver.value = true
}
function onDragLeave() {
  dragCounter--
  if (dragCounter === 0) isDraggingOver.value = false
}
function onWindowDrop(e: DragEvent) {
  dragCounter = 0
  isDraggingOver.value = false
  const file = e.dataTransfer?.files[0]
  if (!file) return
  pickFile(file)
  dialogVisible.value = true
}

onMounted(() => {
  window.addEventListener('dragenter', onDragEnter)
  window.addEventListener('dragleave', onDragLeave)
  window.addEventListener('drop', onWindowDrop)
  window.addEventListener('dragover', (e) => e.preventDefault())
})
onUnmounted(() => {
  window.removeEventListener('dragenter', onDragEnter)
  window.removeEventListener('dragleave', onDragLeave)
  window.removeEventListener('drop', onWindowDrop)
})
</script>

<style scoped>
.upload-btn {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid #2a2a2a;
  background: transparent;
  color: #555;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s, color 0.15s;
  font-family: inherit;
}
.upload-btn:hover { border-color: #6e5fdb; color: #6e5fdb; }

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal {
  background: #111;
  border: 1px solid #1e1e1e;
  border-radius: 8px;
  width: 440px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
}

.modal-header { display: flex; align-items: center; justify-content: space-between; }
.modal-title  { font-size: 13px; font-weight: 600; color: #dde1e7; }
.close-btn    { background: none; border: none; color: #444; font-size: 13px; cursor: pointer; padding: 2px 4px; transition: color 0.15s; }
.close-btn:hover { color: #888; }

.drop-zone {
  border: 1px dashed #2a2a2a;
  border-radius: 6px;
  background: #0d0d0d;
  padding: 32px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.drop-zone:hover, .drop-zone--over { border-color: #6e5fdb; }
.drop-zone--has-file { border-style: solid; border-color: #6e5fdb; }

.drop-icon { font-size: 28px; color: #333; }
.drop-text { font-size: 13px; color: #555; }
.drop-text em { color: #6e5fdb; font-style: normal; }
.drop-hint { font-size: 11px; color: #333; }
.file-icon { font-size: 28px; }
.file-name { font-size: 13px; color: #dde1e7; }
.file-size { font-size: 11px; color: #444; }

.field-row  { display: flex; align-items: center; gap: 12px; }
.field-label { font-size: 12px; color: #555; white-space: nowrap; }
.field-input {
  flex: 1;
  background: #0d0d0d;
  border: 1px solid #2a2a2a;
  border-radius: 6px;
  padding: 7px 12px;
  color: #dde1e7;
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.field-input::placeholder { color: #333; }
.field-input:focus { border-color: #6e5fdb; }

.modal-footer { display: flex; justify-content: flex-end; gap: 8px; }
.btn {
  background: transparent;
  border: 1px solid #2a2a2a;
  color: #555;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  transition: border-color 0.15s, color 0.15s;
}
.btn:hover:not(:disabled) { border-color: #6e5fdb; color: #6e5fdb; }
.btn:disabled { opacity: 0.3; cursor: default; }
.btn--primary { background: #6e5fdb; border-color: #6e5fdb; color: #fff; }
.btn--primary:hover:not(:disabled) { background: #5a4cc7; border-color: #5a4cc7; color: #fff; }
.btn--primary:disabled { background: #2a2550; border-color: #2a2550; color: #444; opacity: 1; }

.drag-overlay {
  position: fixed;
  inset: 0;
  background: rgba(13,13,13,0.9);
  border: 2px dashed #6e5fdb;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: all;
}
.drag-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #6e5fdb;
  font-size: 16px;
  font-family: "JetBrains Mono", ui-monospace, monospace;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to       { opacity: 0; }
</style>
