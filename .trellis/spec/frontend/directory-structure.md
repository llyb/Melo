# 目录与进程边界

建议 desktop/ 使用 electron-vite，src/main/index.ts 负责窗口和 HTTP，src/preload/index.ts 暴露固定接口，src/renderer/src/ 放 Vue UI。
renderer 下 pages/AgentPage.vue、components/ChatMessage.vue、composables/useChat.ts 足够；页面无需路由。
IPC 合同放 desktop/src/shared/chat.ts，不能混入 main 的 Node 依赖。
上述路径已实现；测试位于 desktop/tests。

链路：AgentPage → useChat → window.melo.chat → preload IPC → main HTTP → FastAPI。
renderer 无 Node、文件系统、shell 或直接供应商请求。main 验证 IPC sender 和负载，固定后端地址。
BrowserWindow 显式 nodeIntegration=false、contextIsolation=true、sandbox=true；保留 webSecurity，限制导航/新窗口，配置 CSP。
