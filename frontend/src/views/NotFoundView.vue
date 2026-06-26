<template>
  <div class="not-found-page">
    <h1>404</h1>
    <p>页面不存在</p>
    <router-link to="/products" class="btn-primary">返回产品列表</router-link>
  </div>
</template>

<style scoped>
.not-found-page { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:60vh; gap:16px; }
.not-found-page h1 { font-size:72px; color:var(--color-text-secondary); margin:0; }
.not-found-page p { font-size:18px; color:var(--color-text-secondary); }
.not-found-page .btn-primary { display:inline-flex; padding:10px 24px; text-decoration:none; }
</style>
