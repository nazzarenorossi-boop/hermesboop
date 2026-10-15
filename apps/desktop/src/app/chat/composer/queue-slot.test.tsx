import { AssistantRuntimeProvider, useExternalStoreRuntime } from '@assistant-ui/react'
import type { ThreadMessageLike } from '@assistant-ui/react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import type { HermesGateway } from '@/hermes'
import { I18nProvider } from '@/i18n/context'
import { en } from '@/i18n/en'
import { mainComposerScope } from '@/store/composer'
import { $queuedPromptsBySession, getQueuedPrompts } from '@/store/composer-queue'
import { reconcilePendingSubmissions } from '@/store/pending-submissions'

import { renderComposerQueueSlot } from './queue-slot'
import type { ChatBarState } from './types'

import { ChatBar } from './index'

const queueHook = vi.hoisted(() => vi.fn())

vi.mock('./hooks/use-composer-queue', () => ({ useComposerQueue: queueHook }))

afterEach(() => {
  cleanup()
  $queuedPromptsBySession.set({})
  mainComposerScope.clear()
  localStorage.clear()
  queueHook.mockReset()
})

it('Delete on a server-queued card cancels its admission at the authority', async () => {
  reconcilePendingSubmissions('stored', [{ admission_id: 'adm-1', status: 'queued', user: 'later please' }])
  const request = vi.fn(async () => ({ admission_id: 'adm-1', status: 'terminal', outcome: 'cancelled' }))

  render(
    <I18nProvider configClient={{ getConfig: async () => ({}), saveConfig: async () => ({ ok: true }) }}>
      {renderComposerQueueSlot({
        activeQueueSessionKey: 'stored',
        beginQueuedEdit: vi.fn(),
        busy: true,
        drainNextQueued: vi.fn(async () => undefined),
        exitQueuedEdit: vi.fn(),
        gateway: { request } as unknown as HermesGateway,
        queueEdit: null,
        queueParked: false,
        queuedPrompts: getQueuedPrompts('stored'),
        sendQueuedNow: vi.fn(),
        sessionId: 'runtime-1',
        steerQueuedNow: vi.fn(),
        t: en
      })}
    </I18nProvider>
  )

  fireEvent.click(await screen.findByRole('button', { name: /queued/i }))
  fireEvent.click(screen.getByRole('button', { name: en.composer.queueDelete }))

  await vi.waitFor(() =>
    expect(request).toHaveBeenCalledWith('prompt.cancel', { session_id: 'runtime-1', admission_id: 'adm-1' })
  )
})

const chatBarState: ChatBarState = {
  model: { canSwitch: false, model: '', provider: '' },
  tools: { enabled: false, label: '' },
  voice: { enabled: false, active: false }
}

function QueueScopeHarness() {
  const runtime = useExternalStoreRuntime({
    convertMessage: (message: ThreadMessageLike) => message,
    isRunning: true,
    messages: [] as ThreadMessageLike[],
    onNew: async () => {}
  })

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <MemoryRouter>
        <I18nProvider configClient={null} initialLocale="en">
          <ChatBar
            busy
            disabled={false}
            freshDraftKey="fresh-chat"
            gateway={null}
            onCancel={vi.fn()}
            onSubmit={vi.fn(async () => true)}
            queueSessionKey={null}
            sessionId="previous-session"
            state={chatBarState}
          />
        </I18nProvider>
      </MemoryRouter>
    </AssistantRuntimeProvider>
  )
}

it('does not select a previous session queue for a new chat route (#139190)', () => {
  queueHook.mockReturnValue({
    beginQueuedEdit: vi.fn(),
    deliverQueuedNow: vi.fn(),
    drainNextQueued: vi.fn(),
    editingQueuedPrompt: null,
    exitQueuedEdit: vi.fn(),
    queueCurrentDraft: vi.fn(),
    queueEdit: null,
    queueParked: false,
    queuedPrompts: [],
    sendQueuedNow: vi.fn(),
    steerQueuedNow: vi.fn(),
    stepQueuedEdit: vi.fn()
  })
  render(<QueueScopeHarness />)
  expect(queueHook).toHaveBeenCalledWith(expect.objectContaining({ activeQueueSessionKey: 'fresh-chat' }))
})
