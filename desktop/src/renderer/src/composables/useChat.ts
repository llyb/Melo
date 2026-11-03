import { computed, getCurrentScope, onScopeDispose, reactive, ref, shallowRef } from 'vue'
import { failure, validText, type MeloApi, type StoredMessage, type SessionSummary, type SendTurn, type RunSnapshot, type AcceptedRun, type Result, type RunStatus } from '../../../shared/chat'
type ErrorResult = Extract<Result<never>, {ok:false}>
type View = { session: SessionSummary | null; draft: string; messages: StoredMessage[]; before: number | null; loading: boolean; accepting: boolean; pending: SendTurn | null; run: RunSnapshot | AcceptedRun | null; events: RunSnapshot['events']; error: ErrorResult | null; unread: boolean; cursor: number; requestSeq: number; runEpoch: number; failedTurns: {run_id:string;content:string}[] }
const active = (s?: RunStatus) => !!s && ['accepted','running','awaiting_approval','interrupted','needs_reconciliation'].includes(s)
const newView = (session: SessionSummary | null=null): View => ({session,draft:'',messages:[],before:null,loading:false,accepting:false,pending:null,run:null,events:[],error:null,unread:false,cursor:0,requestSeq:0,runEpoch:0,failedTurns:[]})
export function useChat(api: MeloApi=window.melo) {
  const views=reactive(new Map<string,View>()), selectedId=ref<string|null>(null), empty=shallowRef(reactive(newView()))
  const sessions=ref<SessionSummary[]>([]), hasMore=ref(false), listError=ref<ErrorResult|null>(null), creating=ref(false)
  const creationFailures=ref<{id:string;content:string;message:string}[]>([])
  const timers=new Map<string,ReturnType<typeof setTimeout>>(), polling=new Set<string>()
  let disposed=false, navigation=0
  function viewFor(id: string, session?: SessionSummary): View { let v=views.get(id);if(!v){views.set(id,newView(session??null));v=views.get(id)!}return v }
  const current=computed(()=>selectedId.value?viewFor(selectedId.value):empty.value)
  const input=computed({get:()=>current.value.draft,set:(v:string)=>{current.value.draft=v}})
  const messages=computed(()=>current.value.messages), selected=computed(()=>current.value.session)
  const sending=computed(()=>['accepted','running'].includes(current.value.run?.status??''))
  const working=computed(()=>current.value.loading)
  const error=computed(()=>current.value.error)
  const run=computed(()=>current.value.run)
  const events=computed(()=>current.value.events)
  const failedTurns=computed(()=>current.value.failedTurns.filter(f=>f.run_id!==current.value.run?.run_id))
  const pendingMessage=computed(()=>current.value.pending?.content??null)
  const before=computed(()=>current.value.before)
  const canSend=computed(()=>!!input.value.trim()&&!current.value.loading&&!current.value.accepting&&!active(current.value.run?.status))
  const beforeUnload=(event:BeforeUnloadEvent)=>{if(empty.value.draft||empty.value.accepting||[...views.values()].some(v=>v.draft||v.accepting||active(v.run?.status))){event.preventDefault();event.returnValue=''}}
  window.addEventListener('beforeunload',beforeUnload)
  if(getCurrentScope())onScopeDispose(()=>{disposed=true;for(const timer of timers.values())clearTimeout(timer);window.removeEventListener('beforeunload',beforeUnload)})
  function fail(v:View){v.error=failure('IPC_ERROR','桌面连接异常；运行状态未知，请检查后重试。',true)}
  function merge(old:StoredMessage[], incoming:StoredMessage[], prepend=false) {
    const seen=new Set<string>()
    return (prepend?[...incoming,...old]:[...old,...incoming]).filter(m=>{if(seen.has(m.id))return false;seen.add(m.id);return true})
  }
  function updateSummary(v:View,s:SessionSummary) {
    if(!v.session||s.revision>v.session.revision||s.updated_at>=v.session.updated_at)v.session=s
  }
  async function loadSessions(more=false) {
    try {
      const r=await api.listSessions({limit:50,offset:more?sessions.value.length:0})
      if(disposed)return
      if(!r.ok){listError.value=r;return}
      sessions.value=more?[...sessions.value,...r.data.items]:r.data.items;hasMore.value=r.data.has_more;listError.value=null
      for(const s of r.data.items) {
        const v=viewFor(s.id,s);updateSummary(v,s)
        if(s.active_run&&!v.run){v.run=s.active_run;watchRun(s.active_run)}
      }
    } catch {listError.value=failure('IPC_ERROR','会话目录暂不可读。',true)}
  }
  async function poll(rid:string) {
    if(disposed||polling.has(rid))return
    const owner=[...views.entries()].find(([,v])=>v.run?.run_id===rid)
    if(!owner)return
    const [sid,v]=owner
    const epoch=v.runEpoch
    polling.add(rid)
    try {
      const r=await api.getRun(rid,v.cursor)
      if(disposed||v.run?.run_id!==rid||v.runEpoch!==epoch)return
      if(!r.ok){v.error=r;return}
      const snapshot=r.data
      if(snapshot.session_id!==sid)return
      v.run=snapshot;updateSummary(v,snapshot.session)
      const seen=new Set(v.events.map(e=>e.seq))
      v.events=[...v.events,...snapshot.events.filter(e=>!seen.has(e.seq))].slice(-200)
      v.cursor=snapshot.cursor
      if(snapshot.content&&!v.pending)v.pending={turn_id:snapshot.turn_id,content:snapshot.content,expected_revision:snapshot.session.revision}
      if(snapshot.status==='completed') {
        v.messages=merge(v.messages,snapshot.messages);v.pending=null;v.error=null
        v.unread=selectedId.value!==sid
        void loadSessions()
      } else if(snapshot.error) v.error=failure(snapshot.error.code,snapshot.error.message,true)
    } catch {fail(v)}
    finally {
      polling.delete(rid)
      if(!disposed&&v.run?.run_id===rid&&['accepted','running','awaiting_approval'].includes(v.run.status)) {
        const timer=setTimeout(()=>{timers.delete(rid);void poll(rid)},v.runEpoch!==epoch?0:document.hidden||v.run.status==='awaiting_approval'?5000:1000)
        timers.set(rid,timer)
      }
    }
  }
  function watchRun(accepted:AcceptedRun, replace=false) {
    const v=viewFor(accepted.session_id)
    if(v.run&&!replace&&(v.run.run_id!==accepted.run_id||(['completed','failed','abandoned'].includes(v.run.status)&&active(accepted.status))))return
    if(replace){v.runEpoch++;v.requestSeq++;v.loading=false}
    if(v.run?.run_id!==accepted.run_id){v.cursor=0;v.events=[]}
    v.run={...v.run,...accepted}
    const old=timers.get(accepted.run_id);if(old)clearTimeout(old)
    timers.delete(accepted.run_id);void poll(accepted.run_id)
  }
  async function selectSession(id:string) {
    ++navigation;selectedId.value=id
    const v=viewFor(id,sessions.value.find(s=>s.id===id));v.loading=true
    const seq=++v.requestSeq;v.unread=false
    try {
      const r=await api.getSession(id)
      if(disposed||v.requestSeq!==seq)return
      if(!r.ok){v.error=r;return}
      v.failedTurns=[...new Map([...v.failedTurns,...r.data.failed_turns].map(f=>[f.run_id,f])).values()]
      updateSummary(v,r.data.session);v.messages=merge(v.messages,r.data.messages);v.before=r.data.next_before_seq
      if(r.data.session.active_run)watchRun(r.data.session.active_run)
      else if(r.data.pending_turn&&!v.run) {
        const p=r.data.pending_turn
        if(p.content)v.pending={turn_id:p.turn_id,expected_revision:p.expected_revision,content:p.content}
        watchRun({run_id:p.turn_id,turn_id:p.turn_id,session_id:id,status:p.status as RunStatus})
      }
    } catch{fail(v)}finally{if(v.requestSeq===seq)v.loading=false}
  }
  async function initialize(){await loadSessions();if(!selectedId.value&&sessions.value[0])await selectSession(sessions.value[0].id)}
  async function reset() {
    if(creating.value)return
    const nav=++navigation
    creating.value=true
    try {
      const r=await api.createSession()
      if(!r.ok){listError.value=r;return}
      viewFor(r.data.id,r.data)
      if(navigation===nav)selectedId.value=r.data.id
      await loadSessions()
    } catch{listError.value=failure('IPC_ERROR','创建会话失败。',true)}finally{creating.value=false}
  }
  async function send() {
    if(!canSend.value||disposed)return
    const v=current.value
    const content=v.draft
    if(v.run?.status==='failed'&&v.pending&&!v.failedTurns.some(f=>f.run_id===v.run!.run_id))v.failedTurns.push({run_id:v.run.run_id,content:v.pending.content})
    if(!validText(content,8000)){v.error=failure('INVALID_REQUEST','输入最多8000个字符。');return}
    const nav=navigation
    v.draft='';v.accepting=true;v.error=null
    try {
      let session=v.session
      if(!session) {
        const r=await api.createSession()
        if(!r.ok){v.error=r;creationFailures.value.push({id:crypto.randomUUID(),content,message:r.error.message});return}
        session=r.data;views.set(session.id,v);v.session=session;empty.value=reactive(newView())
        if(navigation===nav&&!selectedId.value)selectedId.value=session.id
      }
      const body=v.pending?.content===content&&!v.run? {...v.pending}:{turn_id:crypto.randomUUID(),expected_revision:session.revision,content}
      v.pending=body
      const r=await api.sendTurn(session.id,body)
      if(!r.ok) {
        v.error=r
        if(['BACKEND_TIMEOUT','BACKEND_UNAVAILABLE'].includes(r.error.code)) {
          v.run={run_id:body.turn_id,turn_id:body.turn_id,session_id:session.id,status:'interrupted'}
        } else {v.run=null;if(!v.draft)v.draft=content}
        if(r.error.code==='SESSION_CONFLICT') {const fresh=await api.getSession(session.id);if(fresh.ok){updateSummary(v,fresh.data.session);v.messages=merge(v.messages,fresh.data.messages)}}
        return
      }
      watchRun(r.data,true);void loadSessions()
    } catch{fail(v);if(!v.draft)v.draft=content}
    finally{v.accepting=false}
  }
  async function retry() {
    const v=current.value
    const rid=v.run?.run_id, epoch=v.runEpoch
    if(!v.run){if(v.pending&&v.session){const r=await api.sendTurn(v.session.id,{...v.pending});if(v.runEpoch!==epoch||v.run)return;if(r.ok)watchRun(r.data,true);else v.error=r};return}
    if(v.error?.error.code==='BACKEND_TIMEOUT'||v.error?.error.code==='BACKEND_UNAVAILABLE') {
      if(v.pending&&v.session) {
        const r=await api.sendTurn(v.session.id,{...v.pending})
        if(v.run?.run_id!==rid||v.runEpoch!==epoch)return
        if(r.ok)watchRun(r.data,true);else v.error=r
      }
      return
    }
    const r=await api.resumeRun(v.run.run_id);if(v.run?.run_id!==rid||v.runEpoch!==epoch||['completed','abandoned'].includes(v.run.status))return;if(r.ok){v.error=null;watchRun(r.data,true)}else v.error=r
  }
  function restoreDraft(content?:string) {
    const v=current.value
    const text=content??v.pending?.content
    if(!text)return
    if(v.draft){v.error=failure('DRAFT_NOT_EMPTY','已有新草稿，未覆盖；请先处理当前草稿。');return}
    v.draft=text
  }
  async function renameSession(id:string,title:string):Promise<boolean> {
    const v=viewFor(id)
    try {const r=await api.renameSession(id,title);if(!r.ok){v.error=r;return false};updateSummary(v,r.data);await loadSessions();return true}catch{fail(v);return false}
  }
  async function deleteSession(id:string) {
    const v=viewFor(id)
    try {const r=await api.deleteSession(id);if(!r.ok){v.error=r;return};views.delete(id);await loadSessions();if(selectedId.value===id){selectedId.value=null;if(sessions.value[0])await selectSession(sessions.value[0].id)}}catch{fail(v)}
  }
  async function loadHistory() {
    const v=current.value
    if(!v.session||v.before===null||v.loading)return
    v.loading=true
    try {const r=await api.getSession(v.session.id,{before_seq:v.before});if(r.ok){v.messages=merge(v.messages,r.data.messages,true);v.before=r.data.next_before_seq}else v.error=r}catch{fail(v)}finally{v.loading=false}
  }
  async function decideApproval(aid:string,decision:'approve'|'reject') {
    const v=current.value;if(!v.run)return
    const rid=v.run.run_id,epoch=v.runEpoch
    try {const r=await api.decideApproval(rid,aid,decision);if(v.run?.run_id!==rid||v.runEpoch!==epoch||['completed','abandoned'].includes(v.run.status))return;if(r.ok){v.error=null;watchRun(r.data,true)}else v.error=r}catch{if(v.run?.run_id===rid&&v.runEpoch===epoch)fail(v)}
  }
  async function action(kind:'resume'|'reprepare'|'end') {
    const v=current.value;if(!v.run)return
    const rid=v.run.run_id,epoch=v.runEpoch
    try {
      const fn=kind==='resume'?api.resumeRun:kind==='reprepare'?api.reprepareApproval:api.endRun
      const r=await fn(rid)
      if(v.run?.run_id!==rid||v.runEpoch!==epoch||['completed','abandoned'].includes(v.run.status))return
      if(r.ok){v.error=null;watchRun(r.data,true);if(kind==='end'){v.pending=null;void loadSessions()}}else v.error=r
    }catch{if(v.run?.run_id===rid&&v.runEpoch===epoch)fail(v)}
  }
  async function inspectMutation(call:string) {const v=current.value;if(!v.run)return null;const r=await api.inspectMutation(v.run.run_id,call);if(r.ok)return r.data;v.error=r;return null}
  async function reconcileMutation(call:string,version:string) {const v=current.value;if(!v.run)return;const r=await api.reconcileMutation(v.run.run_id,call,version);if(r.ok){v.error=null;void poll(v.run.run_id)}else v.error=r}
  function statusFor(id:string){return views.get(id)?.run?.status}
  function unreadFor(id:string){return !!views.get(id)?.unread}
  return {input,messages,selected,sessions,sending,working,error,canSend,send,reset,initialize,loadSessions,selectSession,renameSession,deleteSession,loadHistory,hasMore,before,run,events,pendingMessage,failedTurns,retry,restoreDraft,decideApproval,action,inspectMutation,reconcileMutation,statusFor,unreadFor,listError,creating,creationFailures}
}
