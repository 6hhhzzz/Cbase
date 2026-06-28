/**
 * 工具函数测试 — 匹配实际实现
 */
import { describe, it, expect } from 'vitest'
import { ROLE_LABEL_MAP, INGEST_STATUS_TEXT_MAP } from '../utils/constants'
import { fmtTime } from '../utils/datetime'
import { generateUUID } from '../utils/idgen'
import { handleError } from '../utils/errorHandler'

describe('constants', () => {
  it('ROLE_LABEL_MAP has expected roles', () => {
    expect(ROLE_LABEL_MAP.owner).toBe('拥有者')
    expect(ROLE_LABEL_MAP.admin).toBe('管理员')
    expect(ROLE_LABEL_MAP.member).toBe('成员')
  })

  it('INGEST_STATUS_TEXT_MAP has expected statuses', () => {
    expect(INGEST_STATUS_TEXT_MAP.pending).toBe('待处理')
    expect(INGEST_STATUS_TEXT_MAP.processing).toBe('处理中')
    expect(INGEST_STATUS_TEXT_MAP.completed).toBe('已完成')
    expect(INGEST_STATUS_TEXT_MAP.failed).toBe('失败')
  })
})

describe('datetime', () => {
  it('fmtTime formats a Date object in Chinese locale', () => {
    const date = new Date('2024-01-15T10:30:00')
    const result = fmtTime(date)
    expect(result).toContain('2024')
    expect(result).toContain('15')
  })

  it('fmtTime formats a string date', () => {
    const result = fmtTime('2024-03-20T08:00:00')
    expect(result).toContain('2024')
  })

  it('fmtTime returns empty string for falsy input', () => {
    expect(fmtTime(null)).toBe('')
    expect(fmtTime(undefined)).toBe('')
    expect(fmtTime('')).toBe('')
  })
})

describe('idgen', () => {
  it('generateUUID returns a 36-character hex string', () => {
    const uuid = generateUUID()
    expect(uuid).toHaveLength(36)
    expect(uuid).toMatch(/^[0-9a-f-]+$/)
  })

  it('generateUUID produces unique values', () => {
    const ids = new Set(Array.from({ length: 100 }, () => generateUUID()))
    expect(ids.size).toBe(100)
  })
})

describe('handleError', () => {
  it('ignores cancel/close strings', () => {
    // handleError returns undefined for cancel actions (no ElMessage call)
    expect(handleError('cancel')).toBeUndefined()
    expect(handleError('close')).toBeUndefined()
  })

  it('ignores errors with cancel in message', () => {
    expect(handleError({ message: 'user cancel operation' })).toBeUndefined()
  })

  it('ignores non-network errors (handled by interceptor)', () => {
    // Regular API errors are handled by axios interceptor, handleError skips them
    expect(handleError({ message: 'not found' })).toBeUndefined()
  })
})
