<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useChat } from '../composables/useChat'
import ChatMessage from '../components/ChatMessage.vue'
import { validText, type ObsidianStatus, type RunStatus, type Reconciliation } from '../../../shared/chat'
const { input,messages,sending,working,error,canSend,send,reset,sessions,selected,initialize,selectSession,renameSession,deleteSession,hasMore,loadSessions,before,loadHistory,run,events,pendingMessage,failedTurns,retry,restoreDraft,decideApproval,action,inspectMutation,reconcileMutation,statusFor,unreadFor,listError,creating,creationFailures }=useChat()
const editing=ref<{id:string;title:string;saving:boolean;error:string}|null>(null)
async function rename(id:string,title:string){editing.value={id,title,saving:false,error:''};await nextTick();document.getElementById('rename-'+id)?.focus()}
async function saveTitle(){
 const target=editing.value;if(!target||target.saving)return
 if(!validText(target.title.trim(),80)){target.error='标题需为1–80个字符';return}
 target.saving=true
 const ok=await renameSession(target.id,target.title.trim())
 target.saving=false
 if(editing.value===target){if(ok)editing.value=null;else target.error='保存失败，请检查连接后重试'}
}
function renameKey(event:KeyboardEvent){if(event.isComposing)return;if(event.key==='Enter'){event.preventDefault();void saveTitle()}else if(event.key==='Escape'){event.preventDefault();editing.value=null}}
function remove(id:string){if(window.confirm('删除该会话及全部消息和虚拟文件，无法撤销。'))void deleteSession(id)}
const service=ref('正在检查连接'),connected=ref(false),thread=ref<HTMLElement|null>(null)
const obsidian=ref<ObsidianStatus>({enabled:false,status:'connecting',write_supported:false})
const checkingObsidian=ref(false)
async function checkObsidian(reconnect=false){checkingObsidian.value=true;try{const r=await(reconnect?window.melo.recheckObsidian():window.melo.obsidianStatus());if(r.ok)obsidian.value=r.data;else obsidian.value.status='unavailable'}catch{obsidian.value.status='unavailable'}finally{checkingObsidian.value=false}}
async function checkService(){try{const r=await window.melo.health();connected.value=r.ok&&r.data.model_configured;service.value=r.ok?(r.data.model_configured?'本地服务已连接':'模型尚未配置'):r.error.message}catch{service.value='桌面连接异常';connected.value=false}}
const labels:Record<RunStatus,string>={accepted:'已接受',running:'正在思考与执行',awaiting_approval:'等待确认',interrupted:'已中断，待恢复',needs_reconciliation:'笔记写入待核对',completed:'已完成',failed:'失败',abandoned:'已结束'}
const snapshot=computed(()=>run.value&&'approvals' in run.value?run.value:null)
const now=ref(Date.now());const ticker=setInterval(()=>{now.value=Date.now()},1000);onUnmounted(()=>clearInterval(ticker))
const elapsed=computed(()=>snapshot.value?.created_at?Math.max(0,Math.floor((now.value-Date.parse(snapshot.value.created_at))/1000)):0)
const checkingState=computed(()=>snapshot.value&&['accepted','running'].includes(snapshot.value.status)&&now.value-Date.parse(snapshot.value.updated_at??'')>10000)
const inspections=ref<Record<string,Reconciliation>>({})
async function inspect(call:string){const rid=run.value?.run_id;const value=await inspectMutation(call);if(value&&run.value?.run_id===rid)inspections.value[call]=value}
watch(()=>run.value?.run_id,()=>{inspections.value={}})
function keydown(event:KeyboardEvent){if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();void send()}}
watch([()=>messages.value.length,()=>selected.value?.id],async()=>{await nextTick();thread.value?.scrollTo({top:thread.value.scrollHeight,behavior:'smooth'})})
onMounted(()=>{void checkService();void initialize();void checkObsidian()})
</script>
<template>
  <div class="workspace">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">m</span><span>Melo<span class="brand-sub">思考，从对话开始</span></span></div>
      <button class="new-chat" :disabled="creating" @click="reset"><span>＋</span> 新建会话 <span class="button-arrow">↗</span></button>
      <div class="nav-label">工作空间</div><div class="nav-item"><span>◌</span> Agent <span class="nav-dot"></span></div>
      <div class="session-list" aria-label="会话列表">
        <div v-for="session in sessions" :key="session.id" class="session-row" :class="{active:selected?.id===session.id}">
          <div v-if="editing?.id===session.id" class="inline-title" @click.stop>
            <input :id="'rename-'+session.id" v-model="editing.title" aria-label="会话标题" :disabled="editing.saving" @keydown="renameKey" />
            <button type="button" :disabled="editing.saving" aria-label="保存会话标题" @click.stop="saveTitle">√</button>
            <button type="button" aria-label="取消修改标题" @click.stop="editing=null">×</button>
            <small v-if="editing.error" role="alert">{{ editing.error }}</small>
          </div>
          <template v-else>
            <button :aria-current="selected?.id===session.id?'page':undefined" @click="selectSession(session.id)" @dblclick="rename(session.id,session.title)">{{ session.title }} <span v-if="statusFor(session.id)" class="run-badge">{{ labels[statusFor(session.id)!] }}</span><span v-if="unreadFor(session.id)" aria-label="有新回复"> ●</span></button>
            <button :aria-label="'重命名 '+session.title" @click.stop="rename(session.id,session.title)">✎</button>
            <button :aria-label="'删除 '+session.title" @click.stop="remove(session.id)">×</button>
          </template>
        </div>
        <button v-if="hasMore" @click="loadSessions(true)">加载更多会话</button>
      </div>
      <div v-if="listError" class="directory-error" role="alert">{{ listError.error.message }}<button @click="loadSessions()">重新加载</button></div>
      <div class="sidebar-bottom">
        <button class="obsidian-status" :disabled="checkingObsidian" @click="checkObsidian(true)">Obsidian · {{ obsidian.status==='ready'?'已连接':obsidian.status==='disabled'?'未启用':obsidian.status==='connecting'?'检查中':'未连接，点击检查' }}</button>
        <div class="local-badge">本地开发版 <span>最多5会话并发</span></div><p>留一点空间，给新的想法。</p>
      </div>
    </aside>
    <main class="main-panel">
      <header class="topbar"><div><span class="breadcrumb">工作空间 / </span>{{ selected?.title||'Agent' }}</div><button class="connection" :class="{connected}" @click="checkService"><i></i>{{ service }}</button></header>
      <div ref="thread" class="thread" aria-live="polite" aria-relevant="additions text">
        <button v-if="before!==null" :disabled="working" @click="loadHistory">加载更早消息</button>
        <section v-if="!messages.length&&!pendingMessage" class="welcome">
          <span class="eyebrow">A LITTLE SPACE TO THINK</span><div class="welcome-symbol">m<span>✳</span></div>
          <h1>你好，有什么新想法？</h1><p>一个问题、一点灵感，或者一件还没想清楚的事。<br>从这里开始，我们一起慢慢理顺。</p>
          <div class="suggestions"><button @click="input='帮我把一个模糊的想法梳理成清晰的步骤'">梳理一个想法 <span>↗</span></button><button @click="input='搜索Obsidian中与当前项目相关的笔记'">查找Obsidian笔记 <span>↗</span></button></div>
        </section>
        <div v-else class="message-list">
          <ChatMessage v-for="message in messages" :key="message.id" :message="message" />
          <section v-for="failed in failedTurns" :key="failed.run_id" class="failed-turn">
            <ChatMessage :message="{role:'user',content:failed.content}" /><p>此前一轮未完成 <button @click="restoreDraft(failed.content)">恢复原输入</button></p>
          </section>
          <ChatMessage v-if="pendingMessage" :message="{role:'user',content:pendingMessage}" />
        </div>
        <details v-if="run" class="run-activity" open>
          <summary>{{ labels[run.status] }} <small v-if="elapsed">· 本轮开始于 {{ elapsed }} 秒前</small></summary>
          <p v-if="checkingState" role="status">正在确认运行状态，暂未收到新状态；不会自动重新发送。</p>
          <p v-if="!events.length&&sending" role="status">请求已提交，正在读取后台状态…</p>
          <ol aria-label="执行活动"><li v-for="event in events.filter(e=>e.kind!=='heartbeat')" :key="event.seq">{{ event.label }} <small v-if="event.path">{{ event.path }}</small></li></ol>
          <section v-for="approval in snapshot?.approvals||[]" :key="approval.id" class="approval-card">
            <h3>确认修改笔记 · {{ approval.path }}</h3><p>批准仅用于下方差异和当前版本；Obsidian笔记为真实文件。</p>
            <pre>{{ approval.diff||'差异暂不可读取，请重新检查Obsidian连接。' }}</pre>
            <p v-if="approval.stale||approval.expired" role="alert">笔记已变化或审批已过期，请重新准备修改。</p>
            <button :disabled="approval.stale||approval.expired||approval.decision!==null" @click="decideApproval(approval.id,'approve')">√ 批准这项修改</button>
            <button :disabled="approval.expired||approval.decision!==null" @click="decideApproval(approval.id,'reject')">拒绝</button>
            <small v-if="approval.decision">已记录：{{ approval.decision==='approve'?'批准':'拒绝' }}</small>
          </section>
          <template v-if="run.status==='awaiting_approval'">
            <button @click="action('resume')">决定齐全后继续</button><button @click="action('reprepare')">重新读取并准备修改</button><button @click="action('end')">结束本轮</button>
          </template>
          <div v-for="mutation in snapshot?.mutations||[]" :key="mutation.id" class="mutation-receipt">
            <p>{{ mutation.path }} · {{ mutation.status==='succeeded'?'笔记已写入（不会随回答失败回滚）':mutation.status==='reconciled'?'已接受当前状态，未再次写入':mutation.status }}</p>
            <template v-if="run.status==='needs_reconciliation'&&['unknown','executing'].includes(mutation.status)">
              <button @click="inspect(mutation.id)">核对当前笔记</button>
              <div v-if="inspections[mutation.id]">
                <p>{{ inspections[mutation.id].matches_target?'当前内容与拟写目标一致':'当前内容与目标不同，请先在Obsidian中核对该路径。' }}</p>
                <button @click="reconcileMutation(mutation.id,inspections[mutation.id].observed_version)">接受当前状态，不再执行本次写入</button>
              </div>
            </template>
          </div>
          <template v-if="['failed','interrupted'].includes(run.status)"><button @click="retry">手动恢复本轮</button><button @click="restoreDraft()">恢复原输入</button><button @click="action('end')">结束本轮</button></template>
          <button v-if="run.status==='needs_reconciliation'" @click="action('end')">结束本轮，保留外部笔记</button>
        </details>
      </div>
      <div class="composer-area">
        <div v-for="item in creationFailures" :key="item.id" class="error"><span>{{ item.message }} · 未发送内容已保留</span><button @click="restoreDraft(item.content)">恢复到当前输入</button></div>
        <div v-if="error" class="error" role="alert"><div>{{ error.error.message }}<small>请求编号 {{ error.request_id }}</small></div><button v-if="error.error.retryable" @click="retry">重试 / 检查状态</button></div>
        <form class="composer" @submit.prevent="send">
          <label for="message" class="sr-only">发送给Melo的消息</label><textarea id="message" v-model="input" rows="3" placeholder="把你的想法，留在这里…" @keydown="keydown"></textarea>
          <div class="composer-footer"><span class="model-label"><i></i> Agent · {{ run&&['accepted','running'].includes(run.status)?'本会话运行中，可切换或编辑草稿':'中文对话与Obsidian' }}</span><button class="send-button" type="submit" :disabled="!canSend" aria-label="发送消息">{{ sending?'···':'↑' }}</button></div>
        </form>
        <p class="footnote">Enter发送 · Shift+Enter换行 <span>会话独立运行 · 新草稿不会被后台回复覆盖</span></p>
      </div>
    </main>
  </div>
</template>
