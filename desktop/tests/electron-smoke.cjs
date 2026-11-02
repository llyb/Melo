const { spawn } = require('node:child_process')
const { join } = require('node:path')
const { randomUUID } = require('node:crypto')
const { mkdtempSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { createServer } = require('node:net')
const electron = require('electron')
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
;(async () => {
  const listener = createServer()
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve))
  const port = listener.address().port
  await new Promise(resolve => listener.close(resolve))
  const token = randomUUID()
  const env = { ...process.env, MELO_LOCAL_TOKEN: token, LANGSMITH_TRACING: 'false', SMOKE_PORT: String(port), MELO_TEST_DATA_DIR: mkdtempSync(join(tmpdir(), 'melo-smoke-')) }
  delete env.ELECTRON_RUN_AS_NODE
  const backend = spawn(join(__dirname, '../../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'tests.smoke_server:app', '--host', '127.0.0.1', '--port', String(port), '--no-access-log'], { cwd: join(__dirname, '../../backend'), env, windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
  let diagnostics = ''
  backend.stderr.on('data', data => { diagnostics += data.toString() })
  try {
    let ready = false
    for (let i = 0; i < 150; i++) {
      if (backend.exitCode !== null) throw new Error('Offline backend did not start: ' + diagnostics)
      try { if ((await fetch('http://127.0.0.1:' + port + '/api/v1/health', { headers: { Authorization: 'Bearer ' + token } })).ok) { ready = true; break } } catch { /* Wait for local backend. */ }
      await delay(200)
    }
    if (!ready) throw new Error('Backend readiness timeout')
    const desktop = spawn(electron, [join(__dirname, 'electron-harness.cjs')], { env: { ...env, SMOKE_BACKEND_PID: String(backend.pid) }, windowsHide: true, stdio: 'inherit' })
    const timer = setTimeout(() => desktop.kill(), 60000)
    const exit = await new Promise(resolve => desktop.once('exit', resolve))
    clearTimeout(timer)
    process.exitCode = exit === 0 ? 0 : 1
    if (exit === 0) {
      await delay(500)
      const restoredBackend = spawn(join(__dirname, '../../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'tests.smoke_server:app', '--host', '127.0.0.1', '--port', String(port), '--no-access-log'], { cwd: join(__dirname, '../../backend'), env, windowsHide: true, stdio: 'ignore' })
      try {
        for (let i = 0; i < 150; i++) {
          try { if ((await fetch('http://127.0.0.1:' + port + '/api/v1/health', { headers: { Authorization: 'Bearer ' + token } })).ok) break } catch { /* Wait for restarted backend. */ }
          await delay(100)
        }
        const restoredDesktop = spawn(electron, [join(__dirname, 'electron-restore.cjs')], { env, windowsHide: true, stdio: 'inherit' })
        const restoreTimer = setTimeout(() => restoredDesktop.kill(), 30000)
        const restoredExit = await new Promise(resolve => restoredDesktop.once('exit', resolve))
        clearTimeout(restoreTimer)
        process.exitCode = restoredExit === 0 ? 0 : 1
      } finally { restoredBackend.kill() }
    }
  } catch (error) { console.error(error.message); process.exitCode = 1 }
  finally { backend.kill() }
})()
