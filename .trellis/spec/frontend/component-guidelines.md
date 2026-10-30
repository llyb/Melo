# 组件

使用 Vue 3 SFC + script setup lang="ts"；props 向下、事件向上。AgentPage 管理输入和消息列表，ChatMessage 只展示角色和纯文本。
消息使用稳定本地 ID 作 key，错误不伪装为 assistant 回复。禁止 v-html 渲染模型输出。
输入有 label；发送/新会话按钮可键盘操作；等待和错误使用 aria-live；中文输入法组合期间 Enter 不发送，Shift+Enter 换行。
首版不添加组件库、Markdown 渲染器或设计系统。
