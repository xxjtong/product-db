import { describe, it, expect, vi } from 'vitest'
import { mount, config } from '@vue/test-utils'
import { ref } from 'vue'

// Stub router-link globally
config.global.stubs = { 'router-link': { template: '<a><slot /></a>' } }

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ path: '/test', params: {}, query: {} }),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

// Mock fetch
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({}),
  body: null,
})

describe('PageHeader', () => {
  it('renders title correctly', async () => {
    const PageHeader = (await import('../components/PageHeader.vue')).default
    const wrapper = mount(PageHeader, { props: { title: '测试标题' } })
    expect(wrapper.text()).toContain('测试标题')
  })

  it('renders breadcrumb when provided', async () => {
    const PageHeader = (await import('../components/PageHeader.vue')).default
    const wrapper = mount(PageHeader, {
      props: {
        title: 'Detail',
        breadcrumb: [{ label: '列表', to: '/list' }, { label: 'Detail', to: '' }],
      },
    })
    expect(wrapper.text()).toContain('列表')
    expect(wrapper.text()).toContain('Detail')
  })
})

describe('TagBadge', () => {
  it('renders label text', async () => {
    const TagBadge = (await import('../components/TagBadge.vue')).default
    const wrapper = mount(TagBadge, { props: { label: 'LoRaWAN' } })
    expect(wrapper.text()).toBe('LoRaWAN')
  })
})

describe('ConfirmDialog', () => {
  it('renders title and message when visible', async () => {
    const ConfirmDialog = (await import('../components/ConfirmDialog.vue')).default
    const wrapper = mount(ConfirmDialog, {
      props: { visible: true, title: '删除确认', message: '确定删除吗？' },
    })
    expect(wrapper.text()).toContain('删除确认')
    expect(wrapper.text()).toContain('确定删除吗？')
  })

  it('does not render when not visible', async () => {
    const ConfirmDialog = (await import('../components/ConfirmDialog.vue')).default
    const wrapper = mount(ConfirmDialog, {
      props: { visible: false, title: '删除确认', message: '确定删除吗？' },
    })
    expect(wrapper.text()).not.toContain('确定删除吗？')
  })

  it('emits confirm when confirm button clicked', async () => {
    const ConfirmDialog = (await import('../components/ConfirmDialog.vue')).default
    const wrapper = mount(ConfirmDialog, {
      props: { visible: true, title: '确认', message: '确定？' },
    })
    await wrapper.find('.btn-danger').trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })
})

describe('Pagination', () => {
  it('does not render when total is less than perPage', async () => {
    const Pagination = (await import('../components/Pagination.vue')).default
    const wrapper = mount(Pagination, {
      props: { total: 3, page: 1, perPage: 20 },
    })
    // Pagination should be hidden when there's only 1 page
    expect(wrapper.text()).toBe('')
  })
})

describe('SearchInput', () => {
  it('renders with placeholder', async () => {
    const SearchInput = (await import('../components/SearchInput.vue')).default
    const wrapper = mount(SearchInput, {
      props: { modelValue: '', placeholder: '搜索...' },
    })
    const input = wrapper.find('input')
    expect(input.attributes('placeholder')).toBe('搜索...')
  })
})
