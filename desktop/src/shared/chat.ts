export interface Message { role: 'user' | 'assistant'; content: string }
export interface StoredMessage extends Message { id: string }
export const runStates = ['accepted', 'running', 'awaiting_approval', 'interrupted', 'needs_reconciliation', 'completed', 'failed', 'abandoned'] as const
export type RunStatus = typeof runStates[number]
export interface AcceptedRun { run_id: string; turn_id: string; session_id: string; status: RunStatus }
export interface SessionSummary { id: string; title: string; created_at: string; updated_at: string; revision: number; active_run?: AcceptedRun | null }
export interface SessionDetail { failed_turns: {run_id:string;content:string}[]; session: SessionSummary; messages: StoredMessage[]; has_more: boolean; next_before_seq: number | null; pending_turn: { turn_id: string; status: string; expected_revision: number; content: string | null } | null }
export interface SendTurn { turn_id: string; expected_revision: number; content: string }
export interface RunEvent { seq: number; kind: string; label: string; at: string; path: string | null; session_id: string; run_id: string; turn_id: string }
export interface Approval { id: string; index: number; decision: 'approve' | 'reject' | null; expires_at: number; args_hash: string; path: string; tool: string; expected_version: string; stale: boolean; expired: boolean; diff: string }
export interface Mutation { id: string; path: string; status: string; expected_version: string | null; content_hash: string; args_hash: string; result_version?: string | null; execution_confirmed?: boolean }
export interface RunSnapshot extends AcceptedRun { session: SessionSummary; revision: number; updated_at: string | null; created_at: string | null; spent: number; error: {code: string; message: string} | null; events: RunEvent[]; cursor: number; gap: boolean; messages: StoredMessage[]; content: string | null; approvals: Approval[]; mutations: Mutation[] }
export interface ObsidianStatus { enabled: boolean; status: string; write_supported: boolean }
export interface Reconciliation { id: string; path: string; observed_version: string; matches_target: boolean }
export interface Health { status: 'ok'; model_configured: boolean }
export type Result<T> = { ok: true; data: T } | { ok: false; request_id: string; error: { code: string; message: string; retryable: boolean } }
export interface MeloApi {
  health(): Promise<Result<Health>>
  listSessions(page: {limit: number; offset: number}): Promise<Result<{items: SessionSummary[]; has_more: boolean}>>
  createSession(): Promise<Result<SessionSummary>>
  getSession(id: string, page?: {limit?: number; before_seq?: number}): Promise<Result<SessionDetail>>
  renameSession(id: string, title: string): Promise<Result<SessionSummary>>
  deleteSession(id: string): Promise<Result<{deleted_id: string}>>
  sendTurn(id: string, payload: SendTurn): Promise<Result<AcceptedRun>>
  getRun(id: string, after: number): Promise<Result<RunSnapshot>>
  decideApproval(id: string, aid: string, decision: 'approve' | 'reject'): Promise<Result<AcceptedRun>>
  resumeRun(id: string): Promise<Result<AcceptedRun>>
  reprepareApproval(id: string): Promise<Result<AcceptedRun>>
  endRun(id: string): Promise<Result<AcceptedRun>>
  inspectMutation(id: string, call: string): Promise<Result<Reconciliation>>
  reconcileMutation(id: string, call: string, version: string): Promise<Result<Reconciliation>>
  obsidianStatus(): Promise<Result<ObsidianStatus>>
  recheckObsidian(): Promise<Result<ObsidianStatus>>
}
export const actions = ['health','listSessions','createSession','getSession','renameSession','deleteSession','sendTurn','getRun','decideApproval','resumeRun','reprepareApproval','endRun','inspectMutation','reconcileMutation','obsidianStatus','recheckObsidian'] as const
export type Action = typeof actions[number]
export function isObject(v: unknown): v is Record<string, unknown> { return typeof v === 'object' && v !== null && !Array.isArray(v) }
export function uuid(v: unknown): v is string { return typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v) }
export function validText(v: unknown, max: number): v is string { return typeof v === 'string' && !!v.trim() && [...v].length <= max }
export function accepted(v: unknown): v is AcceptedRun { return isObject(v) && Object.keys(v).length === 4 && uuid(v.run_id) && uuid(v.turn_id) && uuid(v.session_id) && runStates.includes(v.status as RunStatus) }
export function summary(v: unknown): v is SessionSummary { return isObject(v) && Object.keys(v).every(k => ['id','title','created_at','updated_at','revision','active_run'].includes(k)) && uuid(v.id) && validText(v.title,80) && typeof v.created_at === 'string' && typeof v.updated_at === 'string' && Number.isSafeInteger(v.revision) && Number(v.revision)>=0 && (v.active_run === undefined || v.active_run === null || accepted(v.active_run)) }
export function storedMessages(v: unknown): v is StoredMessage[] { return Array.isArray(v) && v.length<=100 && v.length%2===0 && v.every((m,i) => isObject(m) && Object.keys(m).length===3 && typeof m.id==='string' && m.role===(i%2?'assistant':'user') && validText(m.content,i%2?16000:8000)) }
export function failure(code: string, message: string, retryable=false): Extract<Result<never>,{ok:false}> { return {ok:false,request_id:crypto.randomUUID(),error:{code,message,retryable}} }
