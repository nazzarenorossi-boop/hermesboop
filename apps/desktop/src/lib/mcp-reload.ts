import { capabilityScoped, type ProfileScope } from '@/api/client'
import type { HermesGateway } from '@/hermes'
import { sessionOfProfile } from '@/store/session'

/** A turn-isolated session reloads on its compute host, whose own control
 *  budget is 120s; leave headroom above it so the desktop never times out a
 *  reload the host is still completing. */
export const MCP_RELOAD_TIMEOUT_MS = 150_000

type McpReloadStatus = 'confirm_required' | 'reloaded'

export interface McpReloadRequest {
  always?: boolean
  confirm?: boolean
  profile?: ProfileScope
  sessionId?: null | string
}

export interface McpReloadResult {
  failed: string[]
  message: null | string
  status: McpReloadStatus
}

/** The stable prefix an older backend uses to reject `profile` at admission
 *  (`tui_gateway/contracts/registry.py::validate_params`, code 4000, before
 *  the handler runs). Such a backend reloads EVERY profile, so retrying
 *  without it still reaches the target profile. */
const MCP_RELOAD_PROFILE_REJECTION = 'invalid params for reload.mcp: profile:'

const MCP_RELOAD_CONFIRM_WORDS = new Set(['now', 'approve', 'once', 'yes', 'always'])

/** Argument words the desktop forwards for `/reload-mcp`; `always` also
 *  persists the profile's confirmation opt-out. */
export function mcpReloadSlashParams(arg: string, sessionId: string): Record<string, unknown> {
  const choice = arg.trim().toLowerCase()
  const params: Record<string, unknown> = { session_id: sessionId }

  if (MCP_RELOAD_CONFIRM_WORDS.has(choice)) {
    params.confirm = true
  }

  if (choice === 'always') {
    params.always = true
  }

  return params
}

/** Read the fields every `reload.mcp` reply shares. Older backends may omit
 *  any of them, so each is defaulted rather than trusted. Shared by the
 *  request path and the slash renderer so the `failed` filter has one home. */
export function parseMcpReloadResult(response: unknown): {
  failed: string[]
  message: null | string
  status: null | string
} {
  const record = (response ?? {}) as Record<string, unknown>

  return {
    failed: Array.isArray(record.failed)
      ? record.failed.filter((name): name is string => typeof name === 'string')
      : [],
    message: typeof record.message === 'string' ? record.message : null,
    status: typeof record.status === 'string' ? record.status : null
  }
}

/**
 * The one `reload.mcp` caller. The reload acts for `profile` when given, else
 * the profile of `sessionId`, else the launch profile. With `profile` set,
 * `sessionId` is kept only when it belongs to that profile — a foreign id
 * would send the reload to another profile's compute host.
 *
 * A backend predating the `profile` param rejects the whole call at admission
 * and then reloads EVERY profile in the process, so dropping `profile` and
 * retrying ONCE is always safe (the target profile reloads too). Matched on
 * the stable prefix, not `isOutOfSyncRpcParams`: the older backend predates
 * that suffix. Delete once no supported backend predates `profile`.
 */
export async function requestMcpReload(
  gateway: HermesGateway | null | undefined,
  request: McpReloadRequest = {}
): Promise<McpReloadResult> {
  if (!gateway) {
    throw new Error('Hermes gateway is not connected')
  }

  const profile = capabilityScoped(request.profile).profile
  const sessionId = profile ? sessionOfProfile(request.sessionId, profile) : request.sessionId
  const params: Record<string, unknown> = {}

  if (sessionId) {
    params.session_id = sessionId
  }

  if (profile) {
    params.profile = profile
  }

  if (request.confirm) {
    params.confirm = true
  }

  if (request.always) {
    params.always = true
  }

  const response = await requestWithProfileFallback(gateway, params)
  const { failed, message, status } = parseMcpReloadResult(response)

  if (status !== null && status !== 'reloaded' && status !== 'confirm_required') {
    throw new Error(`unexpected reload.mcp status: ${status}`)
  }

  return {
    failed,
    message,
    status: status === 'confirm_required' ? 'confirm_required' : 'reloaded'
  }
}

async function requestWithProfileFallback(gateway: HermesGateway, params: Record<string, unknown>): Promise<unknown> {
  try {
    return await gateway.request('reload.mcp', params, MCP_RELOAD_TIMEOUT_MS)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)

    if (!('profile' in params) || !message.includes(MCP_RELOAD_PROFILE_REJECTION)) {
      throw error
    }

    const { profile: _dropped, ...withoutProfile } = params

    return gateway.request('reload.mcp', withoutProfile, MCP_RELOAD_TIMEOUT_MS)
  }
}
