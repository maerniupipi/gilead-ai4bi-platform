/**
 * 空间上下文 - 提供全局空间状态管理
 */
import { ref, computed, provide, inject } from 'vue'
import * as spaceApi from '@/api/space'
import { setCurrentSpaceId, getCurrentSpaceId } from './auth'

const SPACE_CONTEXT_KEY = Symbol('spaceContext')

export function createSpaceContext() {
  const currentSpace = ref(null)
  const availableSpaces = ref([])
  const isLoading = ref(false)
  const error = ref(null)

  // 空间切换时的回调函数列表
  const onSpaceChangeCallbacks = ref([])

  const hasSpace = computed(() => currentSpace.value !== null)
  const spaceId = computed(() => currentSpace.value?.id)

  /**
   * 注册空间切换回调
   * @param {Function} callback - 回调函数，会接收 newSpaceId 参数
   * @returns {Function} 取消注册的函数
   */
  function onSpaceChange(callback) {
    onSpaceChangeCallbacks.value.push(callback)
    // 返回取消注册的函数
    return () => {
      const idx = onSpaceChangeCallbacks.value.indexOf(callback)
      if (idx !== -1) {
        onSpaceChangeCallbacks.value.splice(idx, 1)
      }
    }
  }

  /**
   * 触发空间切换回调
   */
  function _triggerSpaceChange(newSpaceId) {
    onSpaceChangeCallbacks.value.forEach(cb => {
      try {
        cb(newSpaceId)
      } catch (e) {
        console.error('空间切换回调执行失败:', e)
      }
    })
  }

  async function loadSpaces() {
    isLoading.value = true
    error.value = null
    try {
      const data = await spaceApi.getSpaces()
      availableSpaces.value = data.spaces || []
      // 设置当前空间
      if (data.current_space_id) {
        const current = availableSpaces.value.find(s => s.id === data.current_space_id)
        currentSpace.value = current || null
        setCurrentSpaceId(data.current_space_id)
      } else if (availableSpaces.value.length > 0) {
        // 如果后端没有返回当前空间但有可用空间，选择第一个
        currentSpace.value = availableSpaces.value[0]
        setCurrentSpaceId(availableSpaces.value[0].id)
      }
    } catch (e) {
      error.value = e.message
      console.error('加载空间列表失败:', e)
    } finally {
      isLoading.value = false
    }
  }

  async function switchSpace(newSpaceId) {
    isLoading.value = true
    error.value = null
    try {
      const space = await spaceApi.switchSpace(newSpaceId)
      currentSpace.value = space
      setCurrentSpaceId(newSpaceId)
      // 更新本地列表中的当前空间状态
      const idx = availableSpaces.value.findIndex(s => s.id === newSpaceId)
      if (idx !== -1) {
        availableSpaces.value.forEach((s, i) => {
          if (i === idx) {
            s.is_current = true
          } else {
            s.is_current = false
          }
        })
      }
      // 触发空间切换回调
      _triggerSpaceChange(newSpaceId)
      return space
    } catch (e) {
      error.value = e.message
      console.error('切换空间失败:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function createSpace(spaceData) {
    isLoading.value = true
    error.value = null
    try {
      const newSpace = await spaceApi.createSpace(spaceData)
      availableSpaces.value.push(newSpace)
      return newSpace
    } catch (e) {
      error.value = e.message
      console.error('创建空间失败:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function updateSpace(spaceId, spaceData) {
    isLoading.value = true
    error.value = null
    try {
      const updated = await spaceApi.updateSpace(spaceId, spaceData)
      const idx = availableSpaces.value.findIndex(s => s.id === spaceId)
      if (idx !== -1) {
        availableSpaces.value[idx] = { ...availableSpaces.value[idx], ...updated }
      }
      if (currentSpace.value?.id === spaceId) {
        currentSpace.value = { ...currentSpace.value, ...updated }
      }
      return updated
    } catch (e) {
      error.value = e.message
      console.error('更新空间失败:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function deleteSpace(spaceId, confirmName) {
    isLoading.value = true
    error.value = null
    try {
      const res = await spaceApi.deleteSpace(spaceId, { confirm_name: confirmName })
      if (res?.status === 'deleted') {
        availableSpaces.value = availableSpaces.value.filter(s => s.id !== spaceId)
        if (currentSpace.value?.id === spaceId) {
          currentSpace.value = availableSpaces.value[0] || null
        }
      }
      return res
    } catch (e) {
      error.value = e.message
      console.error('删除空间失败:', e)
      throw e
    } finally {
      isLoading.value = false
    }
  }

  const context = {
    currentSpace,
    availableSpaces,
    spaceId,
    hasSpace,
    isLoading,
    error,
    loadSpaces,
    switchSpace,
    createSpace,
    updateSpace,
    deleteSpace,
    onSpaceChange
  }

  return context
}

export function provideSpaceContext() {
  const context = createSpaceContext()
  provide(SPACE_CONTEXT_KEY, context)
  return context
}

export function useSpaceContext() {
  const context = inject(SPACE_CONTEXT_KEY)
  if (!context) {
    // 如果没有provider，返回一个默认的context
    return createSpaceContext()
  }
  return context
}
