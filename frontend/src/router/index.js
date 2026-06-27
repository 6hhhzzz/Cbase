import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guest: true },
  },
  {
    path: '/spaces',
    name: 'SpaceSwitcher',
    component: () => import('../views/SpaceSwitcher.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    redirect: '/spaces',
  },
  // v4: 全局用户组管理
  {
    path: '/groups',
    name: 'GroupManagement',
    component: () => import('../views/GroupManagement.vue'),
    meta: { requiresAuth: true },
  },
  // v4: 角色管理
  {
    path: '/roles',
    name: 'RoleManagement',
    component: () => import('../views/RoleManagement.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/app/:spaceId/chat',
    name: 'ChatNew',
    component: () => import('../views/Chat.vue'),
    meta: { requiresAuth: true, requiresSpace: true },
  },
  {
    path: '/app/:spaceId/chat/:convId',
    name: 'Chat',
    component: () => import('../views/Chat.vue'),
    meta: { requiresAuth: true, requiresSpace: true },
  },
  {
    path: '/app/:spaceId/documents',
    name: 'Documents',
    component: () => import('../views/Documents.vue'),
    meta: { requiresAuth: true, requiresSpace: true },
  },
  {
    path: '/app/:spaceId/approvals',
    name: 'Approvals',
    component: () => import('../views/Approvals.vue'),
    meta: { requiresAuth: true, requiresSpace: true, requiresAdmin: true },
  },
  // v4: ACE 矩阵配置
  {
    path: '/app/:spaceId/aces',
    name: 'AceConfig',
    component: () => import('../views/AceConfig.vue'),
    meta: { requiresAuth: true, requiresSpace: true },
  },
  {
    path: '/app/:spaceId/settings',
    name: 'SpaceSettings',
    component: () => import('../views/SpaceSettings.vue'),
    meta: { requiresAuth: true, requiresSpace: true },
  },
  {
    path: '/admin',
    name: 'AdminDashboard',
    component: () => import('../views/AdminDashboard.vue'),
    meta: { requiresAuth: true, requiresGlobalAdmin: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.guest && authStore.isLoggedIn) {
    next('/spaces')
    return
  }

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
    return
  }

  if (to.meta.requiresSpace && !authStore.hasActiveSpace) {
    next('/spaces')
    return
  }

  // v4: requiresAdmin → owner 或 admin 都通过（需 Space 上下文）
  if (to.meta.requiresAdmin && !authStore.isSpaceAdmin) {
    next(to.params.spaceId ? `/app/${to.params.spaceId}/documents` : '/spaces')
    return
  }

  // v4: requiresGlobalAdmin → 全局管理员（无需 Space 上下文）
  if (to.meta.requiresGlobalAdmin && !authStore.isGlobalAdmin) {
    next('/spaces')
    return
  }

  next()
})

export default router
