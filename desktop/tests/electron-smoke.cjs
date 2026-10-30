const { spawn } = require('node:child_process')
const { join } = require('node:path')
const { randomUUID } = require('node:crypto')
const electron = require('electron')
const token = randomUUID()
const env = { ...process.env, MELO_LOCAL_TOKEN: token, LANGSMITH_TRACING: 'false' }
delete env.ELECTRON_RUN_AS_NODE
const backend = spawn(join(__dirname, '../../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'tests.smoke_server:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'], { cwd: join(__dirname, '../../backend'), env, windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
;(async () => {
  try {
    let ready = false
    for (let i = 0; i < 150; i++) {
      if (backend.exitCode !== null) throw new Error('Offline backend did not start; check port 8000.')
      try {
        const response = await fetch('http://127.0.0.1:8000/api/v1/health', { headers: { Authorization: `Bearer ${token}` } })
        if (response.ok) { ready = true; break }
      } catch { /* Wait for the local test process. */ }
      await delay(200)
    }
    if (!ready) throw new Error('Backend readiness timeout')
    const desktop = spawn(electron, [join(__dirname, 'electron-harness.cjs')], { env: { ...env, SMOKE_BACKEND_PID: String(backend.pid) }, windowsHide: true, stdio: 'inherit' })
    const timer = setTimeout(() => desktop.kill(), 45000)
    const exit = await new Promise(resolve => desktop.once('exit', resolve))
    clearTimeout(timer)
    process.exitCode = exit === 0 ? 0 : 1
  } catch (error) { console.error(error.message); process.exitCode = 1 }
  finally { backend.kill() }
})()
