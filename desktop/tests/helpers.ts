import { vi } from 'vitest'
import { failure, type MeloApi, type SessionSummary, type RunSnapshot, type SendTurn, type Result } from '../src/shared/chat'
export const ok=<T>(data:T):Result<T>=>({ok:true,data})
export function makeSession(title='A'):SessionSummary{return {id:crypto.randomUUID(),title,revision:0,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),active_run:null}}
export function mockApi(initial:SessionSummary[]=[makeSession()]){
 let rows=[...initial]
 const runs=new Map<string,RunSnapshot>()
 const history=new Map<string,RunSnapshot['messages']>()
 const api:MeloApi={
  health:vi.fn(async()=>ok({status:'ok' as const,model_configured:true})),
  obsidianStatus:vi.fn(async()=>ok({enabled:false,status:'disabled',write_supported:false})),
  recheckObsidian:vi.fn(async()=>ok({enabled:false,status:'disabled',write_supported:false})),
  listSessions:vi.fn(async()=>ok({items:[...rows],has_more:false})),
  createSession:vi.fn(async()=>{const s=makeSession('新会话');rows.unshift(s);return ok(s)}),
  getSession:vi.fn(async(id)=>{const s=rows.find(v=>v.id===id);return s?ok({session:s,messages:history.get(id)??[],has_more:false,next_before_seq:null,pending_turn:null,failed_turns:[]}):failure('SESSION_NOT_FOUND','missing')}),
  renameSession:vi.fn(async(id,title)=>{const s=rows.find(v=>v.id===id)!;s.title=title;return ok({...s})}),
  deleteSession:vi.fn(async(id)=>{rows=rows.filter(s=>s.id!==id);return ok({deleted_id:id})}),
  sendTurn:vi.fn(async(id,payload:SendTurn)=>{
   const s=rows.find(v=>v.id===id)!
   const accepted={run_id:payload.turn_id,turn_id:payload.turn_id,session_id:id,status:'running' as const}
   if(!runs.has(payload.turn_id))runs.set(payload.turn_id,{...accepted,session:{...s},revision:1,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),spent:0,error:null,events:[],cursor:0,gap:false,messages:[],content:payload.content,approvals:[],mutations:[]})
   return ok(accepted)
  }),
  getRun:vi.fn(async(id)=>runs.has(id)?ok(runs.get(id)!):failure('RUN_NOT_FOUND','missing')),
  decideApproval:vi.fn(),resumeRun:vi.fn(),reprepareApproval:vi.fn(),endRun:vi.fn(),inspectMutation:vi.fn(),reconcileMutation:vi.fn()
 }
 function complete(id:string,answer='answer') {
  const r=runs.get(id)!
  const session=rows.find(s=>s.id===r.session_id)!
  session.revision++
  const messages=[{id:crypto.randomUUID(),role:'user' as const,content:r.content!},{id:crypto.randomUUID(),role:'assistant' as const,content:answer}]
  history.set(session.id,[...(history.get(session.id)??[]),...messages])
  runs.set(id,{...r,status:'completed',session:{...session},messages,content:null})
 }
 return {api,runs,complete,history}
}
