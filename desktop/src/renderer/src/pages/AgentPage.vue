<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useChat } from '../composables/useChat'
import ChatMessage from '../components/ChatMessage.vue'

const { input, messages, sending, error, canSend, send, reset } = useChat()
const service = ref('正在检查连接')
const connected = ref(false)
const thread = ref<HTMLElement | null>(null)
async function checkService(): Promise<void> {
  try {
    const result = await window.melo.health()
    connected.value = result.ok && result.data.model_configured
    service.value = result.ok ? (result.data.model_configured ? '本地服务已连接' : '模型尚未配置') : result.error.message
  } catch { service.value = '桌面连接异常，请重新启动应用。'; connected.value = false }
}
function keydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); void send() }
}
watch([() => messages.value.length, sending], async () => {
  await nextTick()
  thread.value?.scrollTo({ top: thread.value.scrollHeight, behavior: 'smooth' })
})
onMounted(checkService)
</script>
<template>
  <div class="workspace">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">m</span><span>Melo<span class="brand-sub">思考，从对话开始</span></span></div>
      <button class="new-chat" :disabled="sending" @click="reset"><span>＋</span> 新建会话 <span class="button-arrow">↗</span></button>
      <div class="nav-label">工作空间</div>
      <div class="nav-item"><span>◌</span> Agent <span class="nav-dot"></span></div>
      <div class="sidebar-bottom"><div class="local-badge">本地开发版 <span>0.1</span></div><p>留一点空间，给新的想法。</p></div>
    </aside>
    <main class="main-panel">
      <header class="topbar"><div><span class="breadcrumb">工作空间 / </span>Agent</div><button class="connection" :class="{ connected }" @click="checkService"><i></i>{{ service }}</button></header>
      <div ref="thread" class="thread" aria-live="polite" aria-relevant="additions text">
        <section v-if="!messages.length && !sending" class="welcome">
          <span class="eyebrow">A LITTLE SPACE TO THINK</span>
          <div class="welcome-symbol">m<span>✳</span></div>
          <h1>你好，有什么新想法？</h1>
          <p>一个问题、一点灵感，或者一件还没想清楚的事。<br>从这里开始，我们一起慢慢理顺。</p>
          <div class="suggestions"><button @click="input = '帮我把一个模糊的想法梳理成清晰的步骤'">梳理一个想法 <span>↗</span></button><button @click="input = '用简单的例子解释一个复杂概念'">理解一个概念 <span>↗</span></button></div>
        </section>
        <div v-else class="message-list">
          <ChatMessage v-for="message in messages" :key="message.id" :message="message" />
          <ChatMessage v-if="sending" :message="{ role: 'user', content: input }" />
          <div v-if="sending" class="thinking" role="status"><span class="avatar">m</span><span class="thinking-dot"></span>Melo 正在思考…</div>
        </div>
      </div>
      <div class="composer-area">
        <div v-if="error" class="error" role="alert"><div>{{ error.error.message }}<small>请求编号 {{ error.request_id }}</small></div><button v-if="error.error.retryable" :disabled="sending" @click="send">重试</button></div>
        <form class="composer" @submit.prevent="send">
          <label for="message" class="sr-only">发送给 Melo 的消息</label>
          <textarea id="message" v-model="input" :disabled="sending" rows="3" placeholder="把你的想法，留在这里…" @keydown="keydown"></textarea>
          <div class="composer-footer"><span class="model-label"><i></i> GLM <span>· 纯文本对话</span></span><button class="send-button" type="submit" :disabled="!canSend" :aria-label="sending ? '正在回复' : '发送消息'">{{ sending ? '···' : '↑' }}</button></div>
        </form>
        <p class="footnote">Enter 发送 · Shift + Enter 换行 <span>当前会话暂不保存，关闭或刷新后清空</span></p>
      </div>
    </main>
  </div>
</template>
