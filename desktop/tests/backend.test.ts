import { expect, it, vi } from 'vitest'
import { backendRequest, isTrustedSender } from '../src/main/backend'

it('allows only the expected main frame', () => {
  expect(isTrustedSender(1, 1, true, 'http://localhost:5173/', 'http://localhost:5173/')).toBe(true)
  expect(isTrustedSender(2, 1, true, 'http://localhost:5173/', 'http://localhost:5173/')).toBe(false)
  expect(isTrustedSender(1, 1, false, 'http://localhost:5173/', 'http://localhost:5173/')).toBe(false)
  expect(isTrustedSender(1, 1, true, 'https://evil.test/', 'http://localhost:5173/')).toBe(false)
})

it('keeps token in main and rejects malformed responses', async () => {
  const network = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok', model_configured: true })))
  const result = await backendRequest('health', undefined, 'local-secret', network)
  expect(network.mock.calls[0][0]).toBe('http://127.0.0.1:8000/api/v1/health')
  expect(network.mock.calls[0][1].headers.Authorization).toBe('Bearer local-secret')
  expect(JSON.stringify(result)).not.toContain('local-secret')
  const malformed = await backendRequest('chat', [{ role: 'user', content: 'hi' }], 't',
    vi.fn().mockResolvedValue(new Response('{}')))
  expect(malformed.ok).toBe(false)
})

it('maps connection and timeout errors without exposing raw text', async () => {
  const offline = await backendRequest('health', undefined, 't', vi.fn().mockRejectedValue(new Error('secret')))
  expect(offline).toMatchObject({ ok: false, error: { code: 'BACKEND_UNAVAILABLE' } })
  expect(JSON.stringify(offline)).not.toContain('secret')
  const timeout = await backendRequest('health', undefined, 't', vi.fn().mockRejectedValue(new DOMException('', 'TimeoutError')))
  expect(timeout).toMatchObject({ ok: false, error: { code: 'BACKEND_TIMEOUT' } })
})
