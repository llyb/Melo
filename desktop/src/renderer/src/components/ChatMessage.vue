<script setup lang="ts">
import type { Message } from '../../../shared/chat'
defineProps<{ message: Message }>()
</script>
<template>
  <article class="message" :class="message.role">
    <div class="message-label"><span class="avatar">{{ message.role === 'user' ? '你' : 'm' }}</span>{{ message.role === 'user' ? '你' : 'Melo' }}</div>
    <p>{{ message.content }}</p>
  </article>
</template>
