import { failure, isObject, uuid, validText, summary, storedMessages, type Action, type Result } from '../shared/chat'
export function isTrustedSender(sender: number, expected: number, mainFrame: boolean, url: string, allowed: string): boolean {
  try { return sender === expected && mainFrame && new URL(url).href === new URL(allowed).href } catch { return false }
}
export async function backendRequest(action: Action, args: unknown, token: string, network: typeof fetch = fetch): Promise<Result<unknown>> {
  if (!token) return failure('LOCAL_NOT_CONFIGURED', '请配置本地服务令牌。')
  const p = isObject(args) ? args : {}
  let path = 'sessions', method = 'GET', body: unknown
  const invalid = () => failure('INVALID_REQUEST', '请求参数无效。')
  if (['health', 'createSession'].includes(action) && args !== undefined) return invalid()
  if (action === 'health') path = 'health'
  else if (action === 'listSessions') {
    if (Object.keys(p).some(k => !['limit', 'offset'].includes(k)) || !Number.isInteger(p.limit) || Number(p.limit) < 1 || Number(p.limit) > 100 || !Number.isInteger(p.offset) || Number(p.offset) < 0) return invalid()
    path += '?limit=' + p.limit + '&offset=' + p.offset
  } else if (action === 'createSession') { method = 'POST'; body = {} }
  else {
    if (!uuid(p.id)) return invalid()
    path += '/' + encodeURIComponent(p.id)
    if (action === 'getSession') {
      const page = isObject(p.page) ? p.page : {}
      if (Object.keys(p).some(k => !['id', 'page'].includes(k)) || Object.keys(page).some(k => !['limit', 'before_seq'].includes(k))) return invalid()
      if (page.limit !== undefined && (!Number.isInteger(page.limit) || Number(page.limit) < 1 || Number(page.limit) > 50)) return invalid()
      if (page.before_seq !== undefined && (!Number.isInteger(page.before_seq) || Number(page.before_seq) < 1)) return invalid()
      path += '?limit=' + (page.limit ?? 20) + (page.before_seq === undefined ? '' : '&before_seq=' + page.before_seq)
    } else if (action === 'renameSession') {
      if (Object.keys(p).length !== 2 || !validText(p.title, 80)) return invalid()
      method = 'PATCH'; body = { title: p.title }
    } else if (action === 'deleteSession') { if (Object.keys(p).length !== 1) return invalid(); method = 'DELETE' }
    else {
      if (Object.keys(p).length !== 2 || !isObject(p.payload)) return invalid()
      const t = p.payload
      if (Object.keys(t).length !== 3 || !uuid(t.turn_id) || !Number.isSafeInteger(t.expected_revision) || Number(t.expected_revision) < 0 || !validText(t.content, 8000)) return invalid()
      path += '/turns'; method = 'POST'; body = t
    }
  }
  try {
    const response = await network('http://127.0.0.1:8000/api/v1/' + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(action === 'sendTurn' ? 65000 : 10000), redirect: 'error' })
    const d: unknown = await response.json()
    if (isObject(d)) {
      if (!response.ok && typeof d.request_id === 'string' && isObject(d.error) && typeof d.error.code === 'string' && typeof d.error.message === 'string' && typeof d.error.retryable === 'boolean') return { ok: false, request_id: d.request_id, error: { code: d.error.code, message: d.error.message, retryable: d.error.retryable } }
      let valid = false
      const fields = { health: 2, listSessions: 2, createSession: 5, renameSession: 5, deleteSession: 1, sendTurn: 4, getSession: 5 }
      if (response.ok && Object.keys(d).length !== fields[action]) return failure('INVALID_RESPONSE', '响应字段无效。')
      if (action === 'health') valid = d.status === 'ok' && typeof d.model_configured === 'boolean'
      else if (action === 'listSessions') valid = Array.isArray(d.items) && d.items.every(summary) && typeof d.has_more === 'boolean'
      else if (action === 'createSession' || action === 'renameSession') valid = summary(d)
      else if (action === 'deleteSession') valid = d.deleted_id === p.id
      else if (action === 'sendTurn') valid = summary(d.session) && d.session.id === p.id && storedMessages(d.messages) && d.messages.length === 2 && uuid(d.turn_id) && typeof d.request_id === 'string'
      else valid = summary(d.session) && d.session.id === p.id && storedMessages(d.messages) && typeof d.has_more === 'boolean' && (d.next_before_seq === null || Number.isSafeInteger(d.next_before_seq)) && (d.pending_turn === null || (isObject(d.pending_turn) && uuid(d.pending_turn.turn_id) && ['running', 'failed'].includes(String(d.pending_turn.status))))
      if (response.ok && valid) return { ok: true, data: d }
    }
    return failure('INVALID_RESPONSE', '本地服务返回无效响应，请检查版本。')
  } catch (e) {
    return isObject(e) && ['TimeoutError', 'AbortError'].includes(String(e.name)) ? failure('BACKEND_TIMEOUT', '等待超时，请重试。', true) : failure('BACKEND_UNAVAILABLE', '无法连接本地服务，请先启动后端。', true)
  }
}
