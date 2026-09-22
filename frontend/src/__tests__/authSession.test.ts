import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

// router.push 用 spy 断言跳转（vi.hoisted 保证 mock 工厂里能安全引用）
const mocks = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push, replace: vi.fn() }),
  useRoute: () => ({ path: '/products' }),
}))

const mockOk = (body: unknown) => ({ ok: true, json: async () => body, text: async () => '' })

async function mountApp() {
  const App = (await import('../App.vue')).default
  return shallowMount(App, {
    global: {
      stubs: { 'router-link': { template: '<a><slot /></a>' }, 'router-view': { template: '<span />' } },
      mocks: { $route: { path: '/products' } },
    },
  })
}

// session 成功的一次响应（App 挂载时 loadSession / loadAiStats 各一发）
const sessionOk = () => mockOk({ user: { id: 1, username: 'admin', role: 'admin' }, can_view_cost: true })
const statsOk = () => mockOk({ total: 0, user_count: 0, total_tokens_in: 0, user_tokens_in: 0 })

describe('退出登录', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.push.mockClear()
  })

  it('logout 请求失败时仍清理本地凭据并跳转登录页', async () => {
    localStorage.setItem('token', 'a-token')
    localStorage.setItem('user', JSON.stringify({ id: 1, username: 'admin', role: 'admin' }))
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce(statsOk())
      .mockRejectedValueOnce(new Error('network down'))  // /auth/logout 网络异常
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    await (wrapper.vm as any).logout()
    await flushPromises()

    // 通知过服务端作废 token（即使失败），本地凭据仍必须清干净、人必须回到登录页
    expect(fetchMock).toHaveBeenCalledWith('/product-db/api/auth/logout', expect.objectContaining({ method: 'POST' }))
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('user')).toBeNull()
    expect(mocks.push).toHaveBeenCalledWith('/login')
    wrapper.unmount()
  })

  it('logout 返回 401 时同样能退出', async () => {
    localStorage.setItem('token', 'expired-token')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce(statsOk())
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ detail: 'Not authenticated' }), text: async () => '' })
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    await (wrapper.vm as any).logout()
    await flushPromises()

    expect(localStorage.getItem('token')).toBeNull()
    expect(mocks.push).toHaveBeenCalledWith('/login')
    wrapper.unmount()
  })
})

describe('原生 fetch 通道的 401 也要跳登录（R78）', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.push.mockClear()
  })

  it('/ai/stats 返回 401 时清凭据并跳登录', async () => {
    localStorage.setItem('token', 'expired-token')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ detail: 'Not authenticated' }), text: async () => '' })
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    expect(localStorage.getItem('token')).toBeNull()
    expect(mocks.push).toHaveBeenCalledWith('/login')
    wrapper.unmount()
  })

  it('保存资料返回 401 时清凭据、跳登录，并关掉资料弹窗', async () => {
    localStorage.setItem('token', 'expired-token')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce(statsOk())
      .mockResolvedValueOnce({ ok: false, status: 401, json: async () => ({ detail: 'Not authenticated' }), text: async () => '' })
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.openProfile()
    expect(vm.showProfile).toBe(true)
    vm.profileEmail = 'new@example.com'
    await vm.saveProfile()
    await flushPromises()

    expect(localStorage.getItem('token')).toBeNull()
    expect(mocks.push).toHaveBeenCalledWith('/login')
    // 弹窗挂在 App 层，跳登录后 App 不卸载 —— 不关掉会盖在登录页上
    expect(vm.showProfile).toBe(false)
    wrapper.unmount()
  })
})

describe('导入页的 401（组件内原生 fetch，R78）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('确认导入返回 401 时清凭据（而不是只弹「导入失败」）', async () => {
    localStorage.setItem('token', 'expired-token')
    const toast = vi.fn()
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 401, json: async () => ({ detail: 'Not authenticated' }), text: async () => '',
    }) as any

    const ImportView = (await import('../views/ImportView.vue')).default
    const wrapper = shallowMount(ImportView, { global: { provide: { toast } } })
    const vm = wrapper.vm as any
    vm.mapping = { 0: 'name' }
    vm.rows = [['示例产品']]

    await vm.doImport()
    await flushPromises()

    expect(localStorage.getItem('token')).toBeNull()
    expect(toast).toHaveBeenCalledWith('登录已过期，请重新登录', 'error')
    wrapper.unmount()
  })
})

describe('修改密码后的会话失效', () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.push.mockClear()
  })

  it('改密成功后提示重新登录并清掉已作废的 token', async () => {
    localStorage.setItem('token', 'a-token')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce(statsOk())
      .mockResolvedValueOnce(mockOk({ user: { id: 1, username: 'admin', role: 'admin' } }))  // PUT /auth/profile
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.profileCurPw = 'old-pass-123'
    vm.profileNewPw = 'new-pass-456'
    await vm.saveProfile()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/product-db/api/auth/profile', expect.objectContaining({ method: 'PUT' }))
    expect(localStorage.getItem('token')).toBeNull()
    expect(mocks.push).toHaveBeenCalledWith('/login')
    expect(wrapper.text()).toContain('密码已修改，请重新登录')
    wrapper.unmount()
  })

  it('只改邮箱时不跳转、保留会话', async () => {
    localStorage.setItem('token', 'a-token')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(sessionOk())
      .mockResolvedValueOnce(statsOk())
      .mockResolvedValueOnce(mockOk({ user: { id: 1, username: 'admin', role: 'admin', email: 'new@example.com' } }))
    global.fetch = fetchMock as any

    const wrapper = await mountApp()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.profileEmail = 'new@example.com'
    await vm.saveProfile()
    await flushPromises()

    expect(localStorage.getItem('token')).toBe('a-token')
    expect(mocks.push).not.toHaveBeenCalledWith('/login')
    wrapper.unmount()
  })
})
