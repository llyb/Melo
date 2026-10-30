import { failure, isObject, validMessages, type ChatReply, type Health, type Result } from '../shared/chat'

export function isTrustedSender(sender: number, expected: number, mainFrame: boolean, url: string, allowed: string): boolean {
  return sender === expected && mainFrame && new URL(url).href === new URL(allowed).href
}

export async function backendRequest(action: 'health' | 'chat', messages: unknown, token: string, network: typeof fetch = fetch): Promise<Result<Health | ChatReply>> {
  if (!token) return failure('LOCAL_NOT_CONFIGURED', '请先配置桌面端的本地服务令牌。')
  if (action === 'chat' && !validMessages(messages)) return failure('INVALID_REQUEST', '消息过长或格式无效，请检查输入或新建会话。')
  try {
    const response = await network(`http://127.0.0.1:8000/api/v1/${action}`, {
      method: action === 'chat' ? 'POST' : 'GET',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      ...(action === 'chat' ? { body: JSON.stringify({ messages }) } : {}),
      signal: AbortSignal.timeout(65000), redirect: 'error'
    })
    const data: unknown = await response.json()
    if (isObject(data)) {
      if (!response.ok && typeof data.request_id === 'string' && isObject(data.error) && typeof data.error.code === 'string' && typeof data.error.message === 'string' && typeof data.error.retryable === 'boolean') {
        return { ok: false, request_id: data.request_id, error: { code: data.error.code, message: data.error.message, retryable: data.error.retryable } }
      }
      if (response.ok && action === 'health' && data.status === 'ok' && typeof data.model_configured === 'boolean') return { ok: true, data: { status: 'ok', model_configured: data.model_configured } }
      if (response.ok && action === 'chat' && typeof data.request_id === 'string' && isObject(data.message) && data.message.role === 'assistant' && typeof data.message.content === 'string' && data.message.content.trim() && [...data.message.content].length <= 16000) {
        return { ok: true, data: { request_id: data.request_id, message: { role: 'assistant', content: data.message.content } } }
      }
    }
    return failure('INVALID_RESPONSE', '本地服务返回了无效响应，请检查后端版本。')
  } catch (error) {
    const timeout = isObject(error) && typeof error.name === 'string' && ['TimeoutError', 'AbortError'].includes(error.name)
    return timeout ? failure('BACKEND_TIMEOUT', '等待超时，请稍后重试。', true)
      : failure('BACKEND_UNAVAILABLE', '无法连接本地服务，请先启动 Python 后端。', true)
  }
}
