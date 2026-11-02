const { app, BrowserWindow } = require('electron')
const assert = require('node:assert/strict')
const nativeFetch = globalThis.fetch
globalThis.fetch = (url, options) => nativeFetch(String(url).replace('http://127.0.0.1:8000/', 'http://127.0.0.1:' + process.env.SMOKE_PORT + '/'), options)
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
;(async () => {
  try {
    await app.whenReady()
    await import('../out/main/index.js')
    const window = BrowserWindow.getAllWindows()[0]
    for (let i = 0; i < 150; i++) {
      if (!window.webContents.isLoading() && await window.webContents.executeJavaScript('!!window.melo && !!document.querySelector("textarea")')) break
      await delay(100)
    }
    const listing = await window.webContents.executeJavaScript('window.melo.listSessions({limit:50,offset:0})')
    assert(listing.ok)
    const saved = listing.data.items.find(item => item.revision > 0)
    assert(saved, 'A completed session survived full process restart')
    const detail = await window.webContents.executeJavaScript('window.melo.getSession(' + JSON.stringify(saved.id) + ')')
    assert(detail.ok)
    assert(detail.data.messages.length >= 2)
    console.log('PASS: fresh Electron and backend processes read persisted session through real preload/IPC.')
    app.exit(0)
  } catch (error) { console.error(error.stack); app.exit(1) }
})()
