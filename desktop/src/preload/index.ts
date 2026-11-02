import { contextBridge, ipcRenderer } from 'electron'
import type { MeloApi } from '../shared/chat'
const api: MeloApi = {
 health:()=>ipcRenderer.invoke('melo:health'),
 listSessions:page=>ipcRenderer.invoke('melo:listSessions',page),
 createSession:()=>ipcRenderer.invoke('melo:createSession'),
 getSession:(id,page)=>ipcRenderer.invoke('melo:getSession',{id,page}),
 renameSession:(id,title)=>ipcRenderer.invoke('melo:renameSession',{id,title}),
 deleteSession:id=>ipcRenderer.invoke('melo:deleteSession',{id}),
 sendTurn:(id,payload)=>ipcRenderer.invoke('melo:sendTurn',{id,payload}),
 getRun:(id,after)=>ipcRenderer.invoke('melo:getRun',{id,after}),
 decideApproval:(id,aid,decision)=>ipcRenderer.invoke('melo:decideApproval',{id,aid,decision}),
 resumeRun:id=>ipcRenderer.invoke('melo:resumeRun',{id}),
 reprepareApproval:id=>ipcRenderer.invoke('melo:reprepareApproval',{id}),
 endRun:id=>ipcRenderer.invoke('melo:endRun',{id}),
 inspectMutation:(id,call)=>ipcRenderer.invoke('melo:inspectMutation',{id,call}),
 reconcileMutation:(id,call,version)=>ipcRenderer.invoke('melo:reconcileMutation',{id,call,version}),
 obsidianStatus:()=>ipcRenderer.invoke('melo:obsidianStatus'),
 recheckObsidian:()=>ipcRenderer.invoke('melo:recheckObsidian')
}
contextBridge.exposeInMainWorld('melo',api)
