# 前端质量

实现任务必须提供 npm run lint / typecheck / build 和 npm test -- --run，确切测试场景见 ../guides/testing.md。
build 验证开发产物，不代表已制作安装包。
禁止 VITE_* 注入密钥、暴露 ipcRenderer、任意 URL IPC、v-html 或关闭安全隔离。
按钮禁用之外 main 也要处理重复调用；错误可见、输入可恢复、日志无对话正文或密钥。
