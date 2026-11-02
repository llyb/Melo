const { app, BrowserWindow } = require('electron')
const { writeFileSync, mkdirSync } = require('node:fs')
const { join } = require('node:path')
const assert = require('node:assert/strict')
const { spawn } = require('node:child_process')
app.disableHardwareAcceleration()
let restartedBackend
const nativeFetch = globalThis.fetch
// Test transport only: production URLs remain fixed.
globalThis.fetch = (url, options) => nativeFetch(String(url).replace('http://127.0.0.1:8000/', 'http://127.0.0.1:' + process.env.SMOKE_PORT + '/'), options)

const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
;(async () => {
  try {
    await app.whenReady()
    await import('../out/main/index.js')
    let window
    for (let i = 0; i < 100; i++) {
      window = BrowserWindow.getAllWindows()[0]
      if (window && !window.webContents.isLoading() && window.webContents.getURL()) break
      await delay(100)
    }
    assert(window, 'Electron window created')
    const execute = code => window.webContents.executeJavaScript(code)
    for (let i = 0; i < 100; i++) {
      if (await execute('!!document.querySelector("textarea") && !!window.melo')) break
      await delay(100)
    }
    assert.equal(await execute('typeof window.melo.sendTurn'), 'function')
    assert.equal(await execute('typeof window.require'), 'undefined')
    const health = await execute('window.melo.health()')
    assert.equal(health.ok, true)
    const submit = async text => {
      await execute(`(() => { const el = document.querySelector('textarea'); el.value = ${JSON.stringify(text)}; el.dispatchEvent(new Event('input', {bubbles:true})); })()`)
      await delay(100)
      await execute('document.querySelector("form.composer").requestSubmit()')
      for (let i = 0; i < 100; i++) {
        await delay(100)
        if (await execute('!document.querySelector("textarea").disabled')) return
      }
      throw new Error('UI response timed out')
    }
    await submit('小明')
    assert.equal(await execute('document.querySelectorAll(".message").length'), 2)
    await submit('我是谁')
    assert.equal(await execute('document.querySelectorAll(".message").length'), 4)
    assert.equal(await execute('Array.from(document.querySelectorAll(".assistant p")).at(-1).textContent'), '小明')
    const path = join(__dirname, '../artifacts')
    mkdirSync(path, { recursive: true })
    console.log('PASS: two UI turns through actual preload/IPC and offline Deep Agents.')
    await delay(300)
    try { writeFileSync(join(path, 'chat.png'), (await window.webContents.capturePage()).toPNG()) }
    catch { console.log('NOTE: screenshot capture unavailable in this desktop session.') }
    await execute('document.querySelector(".new-chat").click()')
    await delay(500)
    assert.equal(await execute('document.querySelectorAll(".message").length'), 0)
    const beforeReload = await execute('window.melo.listSessions({limit:50,offset:0})')
    assert(beforeReload.data.items.length >= 2)
    const savedId = beforeReload.data.items.find(s => s.revision === 2).id
    await window.webContents.reload()
    await delay(1000)
    const restored = await execute('window.melo.getSession(' + JSON.stringify(savedId) + ')')
    assert.equal(restored.data.messages.length, 4)
    process.kill(Number(process.env.SMOKE_BACKEND_PID))
    await delay(300)
    assert.equal((await execute('window.melo.health()')).ok, false)
    await submit('恢复测试')
    assert.equal(await execute('document.querySelectorAll(".message").length'), 0)
    assert.equal(await execute('document.querySelector("textarea").value'), '恢复测试')
    assert.equal(await execute('!!document.querySelector("[role=alert]")'), true)
    restartedBackend = spawn(join(__dirname, '../../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'tests.smoke_server:app', '--host', '127.0.0.1', '--port', process.env.SMOKE_PORT, '--no-access-log'], { cwd: join(__dirname, '../../backend'), env: process.env, windowsHide: true, stdio: 'ignore' })
    let ready = false
    for (let i = 0; i < 100; i++) {
      await delay(100)
      if ((await execute('window.melo.health()')).ok) { ready = true; break }
    }
    assert(ready, 'Restarted backend became ready')
    await execute('document.querySelector(".error button").click()')
    for (let i = 0; i < 100; i++) {
      await delay(100)
      if (await execute('document.querySelectorAll(".message").length === 2')) break
    }
    assert.equal(await execute('document.querySelectorAll(".message").length'), 2)
    assert.equal(await execute('document.querySelector("textarea").value'), '')
    await execute('document.querySelector(".new-chat").click()')
    await delay(500)
    try { writeFileSync(join(path, 'welcome.png'), (await window.webContents.capturePage()).toPNG()) }
    catch { /* Functional DOM checks above remain mandatory. */ }
    const restoredAfterBackend = await execute('window.melo.getSession(' + JSON.stringify(savedId) + ')')
    assert.equal(restoredAfterBackend.data.messages.length, 4)
    const deleted = await execute('window.melo.deleteSession(' + JSON.stringify(savedId) + ')')
    assert.equal(deleted.ok, true)
    assert.equal((await execute('window.melo.getSession(' + JSON.stringify(savedId) + ')')).ok, false)
    console.log('PASS: actual Electron preload/IPC, offline two-turn context, reset, backend disconnect, retained input and successful retry after restart.')
    restartedBackend.kill()
    app.exit(0)
  } catch (error) {
    console.error('SMOKE FAILED:', error.stack)
    restartedBackend?.kill()
    app.exit(1)
  }
})()
