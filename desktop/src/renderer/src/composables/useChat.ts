import { computed, getCurrentScope, onScopeDispose, ref } from 'vue'
import { failure, validText, type MeloApi, type StoredMessage, type SessionSummary, type SendTurn } from '../../../shared/chat'
export function useChat(api: MeloApi = window.melo) {
  const input = ref(''), messages = ref<StoredMessage[]>([]), sessions = ref<SessionSummary[]>([])
  const selected = ref<SessionSummary | null>(null), sending = ref(false), working = ref(false)
  const error = ref<ReturnType<typeof failure> | null>(null), hasMore = ref(false), before = ref<number | null>(null)
  const drafts = new Map<string, string>()
  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (input.value || sending.value || [...drafts.values()].some(Boolean)) { event.preventDefault(); event.returnValue = '' }
  }
  window.addEventListener('beforeunload', beforeUnload)
  let pending: SendTurn | null = null, disposed = false, selection = 0
  if (getCurrentScope()) onScopeDispose(() => { disposed = true; window.removeEventListener('beforeunload', beforeUnload) })
  const canSend = computed(() => !sending.value && !working.value && !!input.value.trim())
  function fail(e: unknown) { error.value = failure('IPC_ERROR', '桌面连接异常，请重试。', true); void e }
  async function loadSessions(more = false) {
    const r = await api.listSessions({ limit: 50, offset: more ? sessions.value.length : 0 })
    if (disposed) return
    if (r.ok) { sessions.value = more ? [...sessions.value, ...r.data.items] : r.data.items; hasMore.value = r.data.has_more } else error.value = r
  }
  async function selectSession(id: string) {
    if (sending.value || working.value) return
    working.value = true
    const seq = ++selection
    if (selected.value) drafts.set(selected.value.id, input.value)
    try {
      const r = await api.getSession(id)
      if (disposed || seq !== selection) return
      if (!r.ok) { error.value = r; return }
      selected.value = r.data.session; messages.value = r.data.messages; before.value = r.data.next_before_seq
      const unresolved = r.data.pending_turn
      input.value = drafts.get(id) || unresolved?.content || ''; pending = unresolved?.content ? { turn_id: unresolved.turn_id, expected_revision: unresolved.expected_revision, content: unresolved.content } : null; error.value = null
    } catch (e) { fail(e) } finally { working.value = false }
  }
  async function initialize() { try { await loadSessions(); if (sessions.value[0]) await selectSession(sessions.value[0].id) } catch (e) { fail(e) } }
  async function reset() {
    if (sending.value || working.value) return
    working.value = true
    try {
      const r = await api.createSession()
      if (!r.ok) { error.value = r; return }
      if (selected.value) drafts.set(selected.value.id, input.value)
      selected.value = r.data; messages.value = []; input.value = ''; pending = null; before.value = null; error.value = null
      await loadSessions()
    } catch (e) { fail(e) } finally { working.value = false }
  }
  async function send() {
    if (!canSend.value || disposed) return
    if (!validText(input.value, 8000)) { error.value = failure('INVALID_REQUEST', '输入最多8000个字符。'); return }
    const content = input.value
    if (!selected.value) { await reset(); input.value = content; if (!selected.value) return }
    const session = selected.value
    if (!session) return
    sending.value = true; error.value = null
    pending = pending && pending.content === content ? pending : { turn_id: crypto.randomUUID(), expected_revision: session.revision, content }
    try {
      const r = await api.sendTurn(session.id, pending)
      if (disposed) return
      if (r.ok) {
        selected.value = r.data.session
        const ids = new Set(messages.value.map(m => m.id))
        messages.value.push(...r.data.messages.filter(m => !ids.has(m.id)))
        input.value = ''; drafts.delete(session.id); pending = null
        await loadSessions()
      } else {
        error.value = r
        if (r.error.code === 'SESSION_CONFLICT') {
          const fresh = await api.getSession(session.id)
          if (fresh.ok) { selected.value = fresh.data.session; messages.value = fresh.data.messages; pending = null }
        }
      }
    } catch (e) { fail(e) } finally { sending.value = false }
  }
  async function renameSession(id: string, title: string) {
    if (sending.value || working.value) return
    working.value = true
    try { const r = await api.renameSession(id, title); if (!r.ok) error.value = r; else { if (selected.value?.id === id) selected.value = r.data; await loadSessions() } } catch (e) { fail(e) } finally { working.value = false }
  }
  async function deleteSession(id: string) {
    if (sending.value || working.value) return
    working.value = true
    let choose = false
    try { const r = await api.deleteSession(id); if (!r.ok) { error.value = r; return }; drafts.delete(id); if (selected.value?.id === id) { selected.value = null; messages.value = []; input.value = ''; pending = null; before.value = null; choose = true }; await loadSessions() } catch (e) { fail(e) } finally { working.value = false }
    if (choose && sessions.value[0]) await selectSession(sessions.value[0].id)
  }
  async function loadHistory() {
    if (!selected.value || before.value === null || working.value || sending.value) return
    working.value = true
    try { const r = await api.getSession(selected.value.id, { before_seq: before.value }); if (r.ok) { messages.value = [...r.data.messages, ...messages.value]; before.value = r.data.next_before_seq } else error.value = r } catch (e) { fail(e) } finally { working.value = false }
  }
  return { input, messages, sessions, selected, sending, working, error, canSend, send, reset, initialize, loadSessions, selectSession, renameSession, deleteSession, loadHistory, hasMore, before }
}
