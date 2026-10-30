import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'
import { failure, validMessages, type MeloApi, type Message } from '../../../shared/chat'

export function useChat(api: MeloApi = window.melo) {
  const input = ref('')
  const messages = ref<(Message & { id: string })[]>([])
  const sending = ref(false)
  const error = ref<Extract<Awaited<ReturnType<MeloApi['chat']>>, { ok: false }> | null>(null)
  let disposed = false
  if (getCurrentScope()) onScopeDispose(() => { disposed = true })
  const canSend = computed(() => !sending.value && !!input.value.trim())
  async function send(): Promise<void> {
    if (!canSend.value || disposed) return
    const content = input.value
    const history: Message[] = [...messages.value.map(({ role, content }) => ({ role, content })), { role: 'user', content }]
    if (!validMessages(history)) {
      error.value = failure('INVALID_REQUEST', '消息或上下文超过限制，请缩短输入或新建会话。') as NonNullable<typeof error.value>
      return
    }
    sending.value = true
    error.value = null
    try {
      const result = await api.chat(history)
      if (disposed) return
      if (result.ok) {
        messages.value.push({ id: crypto.randomUUID(), role: 'user', content }, { id: crypto.randomUUID(), ...result.data.message })
        input.value = ''
      } else error.value = result
    } catch {
      error.value = failure('IPC_ERROR', '桌面连接异常，请重试。', true) as NonNullable<typeof error.value>
    } finally { sending.value = false }
  }
  function reset(): void {
    if (sending.value) return
    messages.value = []
    input.value = ''
    error.value = null
  }
  return { input, messages, sending, error, canSend, send, reset }
}
