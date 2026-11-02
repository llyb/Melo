import { effectScope, isProxy } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useChat } from '../src/renderer/src/composables/useChat'
import { makeSession, mockApi, ok } from './helpers'
import { failure } from '../src/shared/chat'
let scopes:ReturnType<typeof effectScope>[]=[]
beforeEach(()=>vi.useFakeTimers({toFake:['setTimeout','clearTimeout']}))
afterEach(()=>{scopes.forEach(s=>s.stop());scopes=[];vi.useRealTimers()})
function stateFor(api:ReturnType<typeof mockApi>['api']){const scope=effectScope();scopes.push(scope);return scope.run(()=>useChat(api))!}
it('clears immediately, allows new/switch while A runs, and never clears B draft on A reply',async()=>{
 const a=makeSession('A'),b=makeSession('B'),mock=mockApi([a,b]),state=stateFor(mock.api)
 await state.selectSession(a.id)
 state.input.value='A prompt'
 const sent=state.send()
 expect(state.input.value).toBe('')
 await sent;await flushPromises()
 expect(state.pendingMessage.value).toBe('A prompt')
 state.input.value='next A draft'
 await state.selectSession(b.id)
 state.input.value='B draft'
 const rid=vi.mocked(mock.api.sendTurn).mock.calls[0][1].turn_id
 mock.complete(rid)
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 expect(state.selected.value?.id).toBe(b.id)
 expect(state.input.value).toBe('B draft')
 expect(state.messages.value).toHaveLength(0)
 await state.selectSession(a.id)
 expect(state.input.value).toBe('next A draft')
 expect(state.messages.value).toHaveLength(2)
 await state.reset()
 expect(state.selected.value?.id).not.toBe(a.id)
})
it('an old detail cannot replace a newer selected view or clear its draft',async()=>{
 const a=makeSession('A'),b=makeSession('B'),mock=mockApi([a,b]),state=stateFor(mock.api)
 let finish!:(v:Awaited<ReturnType<typeof mock.api.getSession>>)=>void
 vi.mocked(mock.api.getSession).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const selecting=state.selectSession(a.id)
 await state.selectSession(b.id)
 state.input.value='B draft'
 finish(ok({session:a,messages:[],has_more:false,next_before_seq:null,pending_turn:null,failed_turns:[]}))
 await selecting
 expect(state.selected.value?.id).toBe(b.id)
 expect(state.input.value).toBe('B draft')
})
it('keeps failed frozen input when a new message is sent and never overwrites a new draft',async()=>{
 const a=makeSession(),mock=mockApi([a]),state=stateFor(mock.api)
 await state.selectSession(a.id);state.input.value='original';await state.send();await flushPromises()
 const rid=vi.mocked(mock.api.sendTurn).mock.calls[0][1].turn_id
 const r=mock.runs.get(rid)!
 mock.runs.set(rid,{...r,status:'failed',error:{code:'UPSTREAM_ERROR',message:'failed'}})
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 state.input.value='new prompt';await state.send();await flushPromises()
 expect(state.failedTurns.value.some(f=>f.content==='original')).toBe(true)
 state.input.value='new draft';state.restoreDraft('original')
 expect(state.input.value).toBe('new draft')
})
it('retains per-session drafts and switches after deleting the selected idle session',async()=>{
 const a=makeSession('A'),b=makeSession('B'),mock=mockApi([a,b]),state=stateFor(mock.api)
 await state.selectSession(a.id);state.input.value='A draft';await state.selectSession(b.id)
 state.input.value='B draft';await state.selectSession(a.id);expect(state.input.value).toBe('A draft')
 await state.deleteSession(a.id);expect(state.selected.value?.id).toBe(b.id);expect(state.input.value).toBe('B draft')
})
it('a delayed end response cannot replace a newer run or clear its frozen prompt',async()=>{
 const a=makeSession(),mock=mockApi([a]),state=stateFor(mock.api)
 await state.selectSession(a.id);state.input.value='old';await state.send();await flushPromises()
 const oldId=vi.mocked(mock.api.sendTurn).mock.calls[0][1].turn_id
 const old=mock.runs.get(oldId)!
 mock.runs.set(oldId,{...old,status:'awaiting_approval'})
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 let finish!:(v:Awaited<ReturnType<typeof mock.api.endRun>>)=>void
 vi.mocked(mock.api.endRun).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const ending=state.action('end')
 mock.runs.set(oldId,{...old,status:'abandoned'})
 await vi.advanceTimersByTimeAsync(5000);await flushPromises()
 state.input.value='new';await state.send();await flushPromises()
 const newId=vi.mocked(mock.api.sendTurn).mock.calls[1][1].turn_id
 finish(ok({run_id:oldId,turn_id:oldId,session_id:a.id,status:'abandoned'}));await ending
 expect(state.run.value?.run_id).toBe(newId)
 expect(state.pendingMessage.value).toBe('new')
})
it('reposts the same frozen turn after an uncertain transport failure',async()=>{
 const a=makeSession(),mock=mockApi([a]),state=stateFor(mock.api)
 vi.mocked(mock.api.sendTurn).mockResolvedValueOnce(failure('BACKEND_UNAVAILABLE','offline',true))
 await state.selectSession(a.id);state.input.value='original';await state.send()
 await state.retry();await flushPromises()
 expect(mock.api.sendTurn).toHaveBeenCalledTimes(2)
 const calls=vi.mocked(mock.api.sendTurn).mock.calls
 expect(calls[1][1]).toEqual(calls[0][1])
 expect(isProxy(calls[1][1])).toBe(false)
 const rid=calls[0][1].turn_id;mock.complete(rid)
 await vi.advanceTimersByTimeAsync(1000);await flushPromises()
 expect(state.messages.value).toHaveLength(2)
})
it('reuses a declined turn as a plain IPC payload when send is clicked again',async()=>{
 const a=makeSession(),mock=mockApi([a]),state=stateFor(mock.api)
 vi.mocked(mock.api.sendTurn).mockResolvedValueOnce(failure('RATE_LIMITED','five slots busy',true))
 await state.selectSession(a.id);state.input.value='prompt';await state.send();await state.send()
 const calls=vi.mocked(mock.api.sendTurn).mock.calls
 expect(calls).toHaveLength(2)
 expect(calls[1][1]).toEqual(calls[0][1])
 expect(isProxy(calls[1][1])).toBe(false)
})
