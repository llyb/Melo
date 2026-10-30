import { contextBridge, ipcRenderer } from 'electron'
import type { MeloApi } from '../shared/chat'

const api: MeloApi = {
  health: () => ipcRenderer.invoke('melo:health'),
  chat: messages => ipcRenderer.invoke('melo:chat', messages)
}
contextBridge.exposeInMainWorld('melo', api)
