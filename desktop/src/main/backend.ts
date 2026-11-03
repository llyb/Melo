import { failure, isObject, uuid, validText, summary, accepted, storedMessages, runStates, type Action, type Result } from '../shared/chat'
export function isTrustedSender(sender: number, expected: number, mainFrame: boolean, url: string, allowed: string): boolean {
  try { return sender===expected && mainFrame && new URL(url).href===new URL(allowed).href } catch { return false }
}
const integer = (v: unknown, min=0, max=Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(v) && Number(v)>=min && Number(v)<=max
export async function backendRequest(action: Action, args: unknown, token: string, network: typeof fetch=fetch): Promise<Result<unknown>> {
  if (!token) return failure('LOCAL_NOT_CONFIGURED','请配置本地服务令牌。')
  const p=isObject(args)?args:{}
  const invalid=()=>failure('INVALID_REQUEST','请求参数无效。')
  let path='sessions', method='GET', body: unknown
  if (['health','createSession','obsidianStatus','recheckObsidian'].includes(action)) {
    if (args!==undefined) return invalid()
    if (action==='health') path='health'
    if (action==='createSession') { method='POST';body={} }
    if (action==='obsidianStatus'||action==='recheckObsidian') { path='obsidian/'+(action==='obsidianStatus'?'status':'recheck');if(action==='recheckObsidian'){method='POST';body={}} }
  } else if (action==='listSessions') {
    if(Object.keys(p).length!==2||!integer(p.limit,1,100)||!integer(p.offset))return invalid()
    path+='?limit='+p.limit+'&offset='+p.offset
  } else {
    if(!uuid(p.id))return invalid()
    const id=encodeURIComponent(p.id)
    if(['getSession','renameSession','deleteSession','sendTurn'].includes(action)) {
      path+='/'+id
      if(action==='getSession') {
        if(Object.keys(p).some(k=>!['id','page'].includes(k))||(p.page!==undefined&&!isObject(p.page)))return invalid()
        const page=isObject(p.page)?p.page:{}
        if(Object.keys(page).some(k=>!['limit','before_seq'].includes(k))||(page.limit!==undefined&&!integer(page.limit,1,50))||(page.before_seq!==undefined&&!integer(page.before_seq,1)))return invalid()
        path+='?limit='+(page.limit??20)+(page.before_seq===undefined?'':'&before_seq='+page.before_seq)
      } else if(action==='renameSession') {
        if(Object.keys(p).length!==2||!validText(p.title,80))return invalid()
        method='PATCH';body={title:p.title}
      } else if(action==='deleteSession') {if(Object.keys(p).length!==1)return invalid();method='DELETE'}
      else {
        if(Object.keys(p).length!==2||!isObject(p.payload))return invalid()
        const t=p.payload
        if(Object.keys(t).length!==3||!uuid(t.turn_id)||!integer(t.expected_revision)||!validText(t.content,8000))return invalid()
        path+='/turns';method='POST';body=t
      }
    } else {
      path='runs/'+id
      if(action==='getRun') {if(Object.keys(p).length!==2||!integer(p.after))return invalid();path+='?after_seq='+p.after}
      else if(action==='decideApproval') {
        if(Object.keys(p).length!==3||!uuid(p.aid)||!['approve','reject'].includes(String(p.decision)))return invalid()
        path+='/approvals/'+encodeURIComponent(p.aid);method='POST';body={decision:p.decision}
      } else if(action==='inspectMutation'||action==='reconcileMutation') {
        if(Object.keys(p).length!==(action==='inspectMutation'?2:3)||!validText(p.call,256))return invalid()
        path+='/reconciliation/'+encodeURIComponent(p.call)
        if(action==='reconcileMutation'){if(!validText(p.version,1024))return invalid();method='POST';body={decision:'accept_current',observed_version:p.version}}
      } else {
        if(Object.keys(p).length!==1)return invalid()
        path+='/'+({resumeRun:'resume',reprepareApproval:'reprepare-approval',endRun:'end'}[action as 'resumeRun'|'reprepareApproval'|'endRun'])
        method='POST';body={}
      }
    }
  }
  try {
    const response=await network('http://127.0.0.1:8000/api/v1/'+path,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(10000),redirect:'error'})
    const d: unknown=await response.json()
    if(isObject(d)) {
      if(!response.ok&&typeof d.request_id==='string'&&isObject(d.error)&&typeof d.error.code==='string'&&typeof d.error.message==='string'&&typeof d.error.retryable==='boolean')return {ok:false,request_id:d.request_id,error:{code:d.error.code,message:d.error.message,retryable:d.error.retryable}}
      let valid=false
      if(action==='health')valid=Object.keys(d).length===2&&d.status==='ok'&&typeof d.model_configured==='boolean'
      else if(action==='obsidianStatus'||action==='recheckObsidian')valid=Object.keys(d).length===3&&typeof d.enabled==='boolean'&&typeof d.write_supported==='boolean'&&['disabled','unconfigured','connecting','ready','auth_failed','tls_error','incompatible','unavailable'].includes(String(d.status))
      else if(action==='listSessions')valid=Object.keys(d).length===2&&Array.isArray(d.items)&&d.items.length<=100&&d.items.every(summary)&&typeof d.has_more==='boolean'
      else if(action==='createSession'||action==='renameSession')valid=summary(d)
      else if(action==='deleteSession')valid=Object.keys(d).length===1&&d.deleted_id===p.id
      else if(action==='sendTurn'||action==='decideApproval'||['resumeRun','reprepareApproval','endRun'].includes(action))valid=accepted(d)&&(action==='sendTurn'?d.session_id===p.id&&isObject(p.payload)&&d.turn_id===p.payload.turn_id:d.run_id===p.id)
      else if(action==='getSession')valid=Array.isArray(d.failed_turns)&&d.failed_turns.length<=20&&d.failed_turns.every(f=>isObject(f)&&Object.keys(f).length===2&&uuid(f.run_id)&&validText(f.content,8000))&&Object.keys(d).length===6&&summary(d.session)&&d.session.id===p.id&&storedMessages(d.messages)&&typeof d.has_more==='boolean'&&(d.next_before_seq===null||integer(d.next_before_seq,1))&&(d.pending_turn===null||(isObject(d.pending_turn)&&uuid(d.pending_turn.turn_id)&&runStates.includes(d.pending_turn.status as never)&&integer(d.pending_turn.expected_revision)&&(d.pending_turn.content===null||validText(d.pending_turn.content,8000))))
      else if(action==='getRun') {
        const allowed=['run_id','turn_id','session_id','status','session','revision','updated_at','created_at','spent','error','events','cursor','gap','messages','content','approvals','mutations']
        valid=Object.keys(d).every(k=>allowed.includes(k))&&d.run_id===p.id&&uuid(d.turn_id)&&uuid(d.session_id)&&runStates.includes(d.status as never)&&summary(d.session)&&d.session.id===d.session_id&&integer(d.revision)&&integer(d.cursor)&&typeof d.gap==='boolean'&&typeof d.spent==='number'&&storedMessages(d.messages)&&(d.content===null||validText(d.content,8000))&&(d.error===null||(isObject(d.error)&&typeof d.error.code==='string'&&typeof d.error.message==='string'))&&Array.isArray(d.events)&&d.events.length<=200&&d.events.every(e=>isObject(e)&&Object.keys(e).length===8&&integer(e.seq,1)&&e.run_id===p.id&&e.session_id===d.session_id&&e.turn_id===d.turn_id&&typeof e.kind==='string'&&typeof e.label==='string'&&typeof e.at==='string'&&(e.path===null||typeof e.path==='string'))&&Array.isArray(d.approvals)&&d.approvals.every(a=>isObject(a)&&uuid(a.id)&&integer(a.index)&&typeof a.expires_at==='number'&&typeof a.path==='string'&&typeof a.diff==='string'&&typeof a.stale==='boolean'&&typeof a.expired==='boolean'&&[null,'approve','reject'].includes(a.decision as never))&&Array.isArray(d.mutations)&&d.mutations.every(m=>isObject(m)&&typeof m.id==='string'&&typeof m.path==='string'&&typeof m.status==='string')
      } else valid=Object.keys(d).length===4&&typeof d.id==='string'&&typeof d.path==='string'&&typeof d.observed_version==='string'&&typeof d.matches_target==='boolean'
      if(response.ok&&valid)return {ok:true,data:d}
    }
    return failure('INVALID_RESPONSE','本地服务返回无效响应，请检查版本。')
  } catch(e) {return isObject(e)&&['TimeoutError','AbortError'].includes(String(e.name))?failure('BACKEND_TIMEOUT','等待超时，请先检查运行状态。',true):failure('BACKEND_UNAVAILABLE','无法连接本地服务，请启动后端。',true)}
}
