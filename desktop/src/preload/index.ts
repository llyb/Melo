import { contextBridge, ipcRenderer } from 'electron'
import type { MeloApi } from '../shared/chat'
const api: MeloApi = {
  health: () => ipcRenderer.invoke('melo:health'),
  listSessions: page => ipcRenderer.invoke('melo:listSessions', page),
  createSession: () => ipcRenderer.invoke('melo:createSession'),
  getSession: (id, page) => ipcRenderer.invoke('melo:getSession', { id, page }),
  renameSession: (id, title) => ipcRenderer.invoke('melo:renameSession', { id, title }),
  deleteSession: id => ipcRenderer.invoke('melo:deleteSession', { id }),
  sendTurn: (id, payload) => ipcRenderer.invoke('melo:sendTurn', { id, payload })
}
contextBridge.exposeInMainWorld('melo', api)
