import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory('/product-db/'),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { guest: true } },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { admin: true } },
    { path: '/', redirect: '/products' },
    { path: '/categories', redirect: '/dictionaries' },
    { path: '/dictionaries', name: 'dictionaries', component: () => import('./views/DictionariesView.vue') },
    { path: '/products', name: 'products', component: () => import('./views/ProductsView.vue') },
    { path: '/products/compare', name: 'product-compare', component: () => import('./views/ProductCompareView.vue') },
    { path: '/products/new', name: 'product-new', component: () => import('./views/ProductFormView.vue') },
    { path: '/products/:id/edit', name: 'product-edit', component: () => import('./views/ProductFormView.vue') },
    { path: '/products/import', name: 'product-import', component: () => import('./views/ImportView.vue') },
    { path: '/products/:id', name: 'product-detail', component: () => import('./views/ProductDetailView.vue') },
    { path: '/suppliers', name: 'suppliers', component: () => import('./views/SuppliersView.vue') },
    { path: '/solutions', name: 'solutions', component: () => import('./views/SolutionsView.vue') },
    { path: '/solutions/:id', name: 'solution-detail', component: () => import('./views/SolutionDetailView.vue') },
    { path: '/quotations', name: 'quotations', component: () => import('./views/QuotationsView.vue') },
    { path: '/quotations/:id', name: 'quotation-detail', component: () => import('./views/QuotationDetailView.vue') },
    { path: '/agent', name: 'agent', component: () => import('./views/AgentView.vue') },
  ],
})

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 < Date.now()
  } catch {
    return false  // can't decode, assume valid (handled by backend 401)
  }
}

function clearAuth() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')

  if (token && isTokenExpired(token)) {
    clearAuth()
    if (!to.meta.guest) {
      next('/login')
      return
    }
  }

  if (!to.meta.guest && !token) {
    next('/login')
    return
  }
  if (to.meta.admin) {
    try {
      const user = JSON.parse(localStorage.getItem('user') || '{}')
      if (user.role !== 'admin') {
        next('/products')
        return
      }
    } catch {
      next('/products')
      return
    }
  }
  next()
})

export default router
