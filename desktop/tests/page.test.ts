import { flushPromises, mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AgentPage from '../src/renderer/src/pages/AgentPage.vue'

it('supports IME, keyboard sending and displays model output as text', async () => {
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { value: vi.fn(), configurable: true })
  const sendTurn = vi.fn().mockResolvedValue({ ok: true, data: { request_id: '1', session: { id: 'id', title: 'hi', revision: 1, created_at: '', updated_at: '' }, messages: [{ id: 'u', role: 'user', content: '你好' }, { id: 'a', role: 'assistant', content: '<script>unsafe</script>' }] } })
  window.melo = { health: vi.fn().mockResolvedValue({ ok: true, data: { status: 'ok', model_configured: true } }), sendTurn, listSessions: vi.fn().mockResolvedValue({ ok: true, data: { items: [], has_more: false } }), createSession: vi.fn().mockResolvedValue({ ok: true, data: { id: 'id', title: '新会话', revision: 0, created_at: '', updated_at: '' } }), getSession: vi.fn(), renameSession: vi.fn(), deleteSession: vi.fn() }
  const page = mount(AgentPage)
  await flushPromises()
  const textarea = page.get('textarea')
  expect(page.get('[aria-label="发送消息"]').attributes('disabled')).toBeDefined()
  await textarea.setValue('你好')
  await textarea.trigger('keydown', { key: 'Enter', isComposing: true })
  await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
  expect(sendTurn).not.toHaveBeenCalled()
  await textarea.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  expect(sendTurn).toHaveBeenCalledTimes(1)
  expect(page.text()).toContain('<script>unsafe</script>')
  expect(page.find('.message script').exists()).toBe(false)
  page.unmount()
})
