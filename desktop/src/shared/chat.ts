export interface Message { role: 'user' | 'assistant'; content: string }
export interface StoredMessage extends Message { id: string }
export interface SessionSummary { id: string; title: string; created_at: string; updated_at: string; revision: number }
export interface SessionDetail { session: SessionSummary; messages: StoredMessage[]; has_more: boolean; next_before_seq: number | null; pending_turn: { turn_id: string; status: string; expected_revision: number; content: string | null } | null }
export interface SendTurn { turn_id: string; expected_revision: number; content: string }
export interface TurnReply { request_id: string; turn_id: string; session: SessionSummary; messages: StoredMessage[] }
export interface ChatReply { request_id: string; message: { role: 'assistant'; content: string } }
export interface Health { status: 'ok'; model_configured: boolean }
export type Result<T> = { ok: true; data: T } | { ok: false; request_id: string; error: { code: string; message: string; retryable: boolean } }
export interface MeloApi {
  health(): Promise<Result<Health>>
  listSessions(page: { limit: number; offset: number }): Promise<Result<{ items: SessionSummary[]; has_more: boolean }>>
  createSession(): Promise<Result<SessionSummary>>
  getSession(id: string, page?: { limit?: number; before_seq?: number }): Promise<Result<SessionDetail>>
  renameSession(id: string, title: string): Promise<Result<SessionSummary>>
  deleteSession(id: string): Promise<Result<{ deleted_id: string }>>
  sendTurn(id: string, payload: SendTurn): Promise<Result<TurnReply>>
}
export const actions = ['health', 'listSessions', 'createSession', 'getSession', 'renameSession', 'deleteSession', 'sendTurn'] as const
export type Action = typeof actions[number]
export function isObject(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v) }
export function uuid(v: unknown): v is string { return typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v) }
export function validText(v: unknown, max: number): v is string { return typeof v === 'string' && !!v.trim() && [...v].length <= max }
export function summary(v: unknown): v is SessionSummary { return isObject(v) && Object.keys(v).length === 5 && uuid(v.id) && validText(v.title, 80) && typeof v.created_at === 'string' && typeof v.updated_at === 'string' && Number.isSafeInteger(v.revision) && Number(v.revision) >= 0 }
export function storedMessages(v: unknown): v is StoredMessage[] {
  return Array.isArray(v) && v.length <= 100 && v.length % 2 === 0 && v.every((m, i) => isObject(m) && Object.keys(m).length === 3 && typeof m.id === 'string' && m.role === (i % 2 ? 'assistant' : 'user') && validText(m.content, i % 2 ? 16000 : 8000))
}
export function failure(code: string, message: string, retryable = false): Extract<Result<never>, { ok: false }> { return { ok: false, request_id: crypto.randomUUID(), error: { code, message, retryable } } }
