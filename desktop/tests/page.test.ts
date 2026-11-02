import { flushPromises,mount } from '@vue/test-utils'
import { expect,it,vi } from 'vitest'
import AgentPage from '../src/renderer/src/pages/AgentPage.vue'
import { makeSession,mockApi } from './helpers'
it('supports IME, immediate clear, background-safe draft and renders model text safely',async()=>{
 Object.defineProperty(HTMLElement.prototype,'scrollTo',{value:vi.fn(),configurable:true})
 const session=makeSession(),mock=mockApi([session]);window.melo=mock.api
 const page=mount(AgentPage);await flushPromises()
 const textarea=page.get('textarea');await textarea.setValue('hello')
 await textarea.trigger('keydown',{key:'Enter',isComposing:true});await textarea.trigger('keydown',{key:'Enter',shiftKey:true})
 expect(mock.api.sendTurn).not.toHaveBeenCalled()
 await textarea.trigger('keydown',{key:'Enter'});await flushPromises()
 expect((textarea.element as HTMLTextAreaElement).value).toBe('')
 expect(textarea.attributes('disabled')).toBeUndefined()
 expect(page.get('.new-chat').attributes('disabled')).toBeUndefined()
 const rid=vi.mocked(mock.api.sendTurn).mock.calls[0][1].turn_id
 mock.complete(rid,'<script>unsafe</script>')
 await new Promise(resolve=>setTimeout(resolve,1100));await flushPromises()
 expect(page.text()).toContain('<script>unsafe</script>');expect(page.find('.message script').exists()).toBe(false)
 page.unmount()
})
it('edits the title inside the sidebar and saves with a checkmark',async()=>{
 const session=makeSession('Old'),mock=mockApi([session]);window.melo=mock.api
 const page=mount(AgentPage);await flushPromises()
 await page.get('[aria-label="重命名 Old"]').trigger('click')
 expect(page.find('.main-panel .title-editor').exists()).toBe(false)
 const input=page.get('.sidebar .inline-title input');await input.setValue('New')
 await input.trigger('keydown',{key:'Enter',isComposing:true});expect(mock.api.renameSession).not.toHaveBeenCalled()
 await page.get('[aria-label="保存会话标题"]').trigger('click');await flushPromises()
 expect(mock.api.renameSession).toHaveBeenCalledWith(session.id,'New')
 expect(page.find('.inline-title').exists()).toBe(false);page.unmount()
})
