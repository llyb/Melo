# Vue composable

项目使用 Vue composable，不使用 React hooks。
useChat.ts 收敛发送、状态、重试和重置，调用 preload 的类型化 API；不要直接访问 fetch 或 ipcRenderer。
先在页面内写简单展示逻辑；不为一次性代码拆通用 hook。组件卸载后忽略旧请求结果，避免污染新页面。
