import { app, BrowserWindow, ipcMain } from 'electron'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { config } from 'dotenv'
import { backendRequest, isTrustedSender } from './backend'
import { failure } from '../shared/chat'

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
  window.webContents.on('will-navigate', (event, url) => { if (url !== allowed) event.preventDefault() })
  window.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false))
  let busy = false
  for (const action of ['health', 'chat'] as const) {
    ipcMain.removeHandler(`melo:${action}`)
    ipcMain.handle(`melo:${action}`, async (event, messages: unknown) => {
      if (!isTrustedSender(event.sender.id, window.webContents.id, event.senderFrame === window.webContents.mainFrame, event.senderFrame?.url || 'about:blank', allowed)) return failure('UNAUTHORIZED', '请求来源无效。')
      if (action === 'chat' && busy) return failure('RATE_LIMITED', '请等待当前回复。', true)
      if (action === 'chat') busy = true
      try { return await backendRequest(action, messages, process.env.MELO_LOCAL_TOKEN || '') }
      finally { if (action === 'chat') busy = false }
    })
  }
  void window.loadURL(allowed)
}

void app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => { if (!BrowserWindow.getAllWindows().length) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
