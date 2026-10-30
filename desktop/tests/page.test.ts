import { flushPromises, mount } from '@vue/test-utils'
import { expect, it, vi } from 'vitest'
import AgentPage from '../src/renderer/src/pages/AgentPage.vue'

it('supports IME, keyboard sending and displays model output as text', async () => {
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', { value: vi.fn(), configurable: true })
  const chat = vi.fn().mockResolvedValue({ ok: true, data: { request_id: '1', message: { role: 'assistant', content: '<script>unsafe</script>' } } })
  window.melo = { health: vi.fn().mockResolvedValue({ ok: true, data: { status: 'ok', model_configured: true } }), chat }
  const page = mount(AgentPage)
  await flushPromises()
  const textarea = page.get('textarea')
  expect(page.get('[aria-label="发送消息"]').attributes('disabled')).toBeDefined()
  await textarea.setValue('你好')
  await textarea.trigger('keydown', { key: 'Enter', isComposing: true })
  await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
  expect(chat).not.toHaveBeenCalled()
  await textarea.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  expect(chat).toHaveBeenCalledTimes(1)
  expect(page.text()).toContain('<script>unsafe</script>')
  expect(page.find('.message script').exists()).toBe(false)
  page.unmount()
})
