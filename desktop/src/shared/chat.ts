export interface Message { role: 'user' | 'assistant'; content: string }
export interface ChatReply { request_id: string; message: { role: 'assistant'; content: string } }
export interface Health { status: 'ok'; model_configured: boolean }
export type Result<T> = { ok: true; data: T } | {
  ok: false; request_id: string; error: { code: string; message: string; retryable: boolean }
}
export interface MeloApi {
  health(): Promise<Result<Health>>
  chat(messages: Message[]): Promise<Result<ChatReply>>
}
export function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
export function validMessages(value: unknown): value is Message[] {
  if (!Array.isArray(value) || !value.length || value.length > 39 || value.length % 2 !== 1) return false
  let total = 0
  return value.every((m, i) => {
    if (!isObject(m) || Object.keys(m).length !== 2 || m.role !== (i % 2 ? 'assistant' : 'user') || typeof m.content !== 'string' || !m.content.trim()) return false
    const length = [...m.content].length
    total += length
    return length <= (m.role === 'user' ? 8000 : 16000) && total <= 64000
  })
}
export function failure(code: string, message: string, retryable = false): Result<never> {
  return { ok: false, request_id: crypto.randomUUID(), error: { code, message, retryable } }
}
