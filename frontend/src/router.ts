import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { guest: true } },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { admin: true } },
    { path: '/', redirect: '/products' },
    { path: '/categories', name: 'categories', component: () => import('./views/CategoriesView.vue') },
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
  ],
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  if (!to.meta.guest && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
