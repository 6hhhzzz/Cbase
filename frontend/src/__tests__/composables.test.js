/**
 * Composable 单元测试 — mock API 调用
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock API module before imports
vi.mock('../api', () => ({
  userApi: { search: vi.fn() },
  authApi: { getAccessibleKBs: vi.fn() },
}))

import { useUserSearch } from '../composables/useUserSearch'
import { useKbFetcher } from '../composables/useKbFetcher'
import { userApi, authApi } from '../api'

describe('useUserSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns empty options for empty query', async () => {
    const { userOptions, searchUsers } = useUserSearch()
    await searchUsers('')
    expect(userOptions.value).toEqual([])
  })

  it('maps API results correctly', async () => {
    vi.mocked(userApi.search).mockResolvedValue({
      data: {
        data: [
          { user_id: '1', username: 'alice', display_name: 'Alice' },
          { user_id: '2', username: 'bob', display_name: 'Bob' },
        ],
      },
    })

    const { userOptions, searchUsers } = useUserSearch()
    await searchUsers('alice')

    expect(userOptions.value).toHaveLength(2)
    expect(userOptions.value[0]).toEqual({
      user_id: '1', username: 'alice', display_name: 'Alice',
    })
  })

  it('handles API errors gracefully', async () => {
    vi.mocked(userApi.search).mockRejectedValue(new Error('Network error'))
    const { userOptions, searchUsers } = useUserSearch()
    await searchUsers('test')
    expect(userOptions.value).toEqual([])
  })

  it('sets searching flag during request', async () => {
    let done
    const promise = new Promise(resolve => { done = resolve })
    vi.mocked(userApi.search).mockReturnValue(promise)
    const { searching, searchUsers } = useUserSearch()

    const p = searchUsers('test')
    expect(searching.value).toBe(true)

    done({ data: { data: [] } })
    await p
    expect(searching.value).toBe(false)
  })
})

describe('useKbFetcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loadKBs fetches accessible KBs', async () => {
    vi.mocked(authApi.getAccessibleKBs).mockResolvedValue({
      data: {
        data: [
          { kb_id: 'kb-1', name: '知识库1', description: '', visibility: 'space_wide' },
          { kb_id: 'kb-2', name: '知识库2', description: '', visibility: 'restricted' },
        ],
      },
    })

    const { kbs, loadKBs } = useKbFetcher()
    await loadKBs()

    expect(kbs.value).toHaveLength(2)
    expect(kbs.value[0].kb_id).toBe('kb-1')
    expect(kbs.value[0].name).toBe('知识库1')
  })

  it('handles errors silently', async () => {
    vi.mocked(authApi.getAccessibleKBs).mockRejectedValue(new Error())
    const { kbs, loadKBs } = useKbFetcher()
    await loadKBs()
    expect(kbs.value).toEqual([])
  })
})
