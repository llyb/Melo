import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { config } from 'dotenv'
import { backendRequest, isTrustedSender } from './backend'
import { actions, failure } from '../shared/chat'

const here = dirname(fileURLToPath(import.meta.url))
config({ path: join(here, '../../.env'), quiet: true })

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1180, height: 820, minWidth: 760, minHeight: 580,
    title: 'Melo · Agent', backgroundColor: '#f7f7f2', autoHideMenuBar: true,
    webPreferences: { preload: join(here, '../preload/index.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true }
  })
  const allowed = process.env.ELECTRON_RENDERER_URL || pathToFileURL(join(here, '../renderer/index.html')).href
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  window.webContents.on('will-prevent-unload', event => {
    if (dialog.showMessageBoxSync(window, { type: 'question', buttons: ['继续编辑', '离开'], defaultId: 0, cancelId: 0, message: '尚有未发送输入或未完成回复，离开后草稿可能丢失。' }) === 1) event.preventDefault()
  })
  window.webContents.on('will-navigate', (event, url) => { if (url !== allowed) event.preventDefault() })
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  for (const action of actions) {
    ipcMain.removeHandler(`melo:${action}`)
    ipcMain.handle(`melo:${action}`, async (event, messages: unknown) => {
      if (!isTrustedSender(event.sender.id, window.webContents.id, event.senderFrame === window.webContents.mainFrame, event.senderFrame?.url || 'about:blank', allowed)) return failure('UNAUTHORIZED', '请求来源无效。')
      return await backendRequest(action, messages, process.env.MELO_LOCAL_TOKEN || '')
    })
  }
  void window.loadURL(allowed)
}

if (!app.requestSingleInstanceLock()) app.quit()
else void app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => { if (!BrowserWindow.getAllWindows().length) createWindow() })
})
app.on('second-instance', () => { const window = BrowserWindow.getAllWindows()[0]; window?.restore(); window?.focus() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
