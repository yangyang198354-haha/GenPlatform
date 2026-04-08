<template>
  <div class="app-shell">
    <!-- Sidebar -->
    <aside class="sidebar">
      <!-- Logo -->
      <div class="sidebar-logo">
        <div class="logo-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
              stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <span class="logo-text">内容生成平台</span>
      </div>

      <!-- Nav -->
      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: activeMenu === item.path }"
        >
          <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="activeMenu === item.path" class="nav-active-dot" />
        </router-link>
      </nav>

      <!-- Bottom -->
      <div class="sidebar-footer">
        <div class="footer-divider" />
        <div class="user-card" @click="handleLogout">
          <el-avatar :size="30" class="user-avatar">
            {{ userInitial }}
          </el-avatar>
          <div class="user-info">
            <span class="user-email">{{ authStore.user?.email }}</span>
            <span class="user-role">内容创作者</span>
          </div>
          <el-icon class="logout-icon"><SwitchButton /></el-icon>
        </div>
      </div>
    </aside>

    <!-- Main area -->
    <div class="main-area">
      <!-- Top bar -->
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">{{ currentPageTitle }}</h1>
        </div>
        <div class="topbar-right">
          <el-badge :value="unreadCount" :hidden="!unreadCount" class="notif-badge">
            <el-button circle class="icon-btn">
              <el-icon><Bell /></el-icon>
            </el-button>
          </el-badge>
          <el-divider direction="vertical" style="height:20px;margin:0 8px" />
          <el-dropdown @command="handleCommand" trigger="click">
            <div class="avatar-trigger">
              <el-avatar :size="32" class="header-avatar">{{ userInitial }}</el-avatar>
              <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <div class="dropdown-user-info">
                  <el-avatar :size="36" class="header-avatar">{{ userInitial }}</el-avatar>
                  <div>
                    <div style="font-weight:600;font-size:13px">{{ authStore.user?.email }}</div>
                    <div style="color:var(--text-muted);font-size:12px">内容创作者</div>
                  </div>
                </div>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- Content -->
      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useNotificationStore } from "@/stores/notification";
import {
  Document, Edit, List, VideoCamera, Setting,
  ArrowDown, SwitchButton, Bell,
} from "@element-plus/icons-vue";

const route   = useRoute();
const router  = useRouter();
const authStore = useAuthStore();
const notifStore = useNotificationStore();

const navItems = [
  { path: "/knowledge-base", label: "知识库",   icon: Document    },
  { path: "/workspace",      label: "内容生成", icon: Edit        },
  { path: "/contents",       label: "内容列表", icon: List        },
  { path: "/videos",         label: "视频项目", icon: VideoCamera },
  { path: "/publish",        label: "发布管理", icon: Bell        },
  { path: "/settings",       label: "系统设置", icon: Setting     },
];

const pageTitles = {
  "/knowledge-base": "知识库",
  "/workspace":      "内容生成工作台",
  "/contents":       "内容列表",
  "/videos":         "视频项目",
  "/publish":        "发布管理",
  "/settings":       "系统设置",
};

const activeMenu      = computed(() => route.path);
const currentPageTitle = computed(() => pageTitles[route.path] || "");
const userInitial     = computed(() => (authStore.user?.email?.[0] || "U").toUpperCase());
const unreadCount     = computed(() => notifStore.notifications?.filter(n => !n.read).length || 0);

async function handleCommand(cmd) {
  if (cmd === "logout") handleLogout();
}
async function handleLogout() {
  authStore.logout();
  router.push("/login");
}
</script>

<style scoped>
/* ── Shell ── */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--surface-base);
}

/* ── Sidebar ── */
.sidebar {
  width: 228px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
/* subtle top-right glow */
.sidebar::before {
  content: '';
  position: absolute;
  top: -60px;
  right: -60px;
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%);
  pointer-events: none;
}

/* Logo */
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 18px 18px;
  border-bottom: 1px solid var(--sidebar-border);
}
.logo-icon {
  width: 32px;
  height: 32px;
  background: var(--brand-gradient);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
  box-shadow: var(--shadow-brand);
}
.logo-text {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-inverse);
  letter-spacing: -0.01em;
  white-space: nowrap;
}

/* Nav */
.sidebar-nav {
  flex: 1;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--sidebar-text);
  font-size: 13.5px;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
  position: relative;
  overflow: hidden;
}
.nav-item::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--sidebar-item-hover);
  opacity: 0;
  border-radius: 8px;
  transition: opacity var(--transition-fast);
}
.nav-item:hover {
  color: var(--sidebar-text-hover);
}
.nav-item:hover::before { opacity: 1; }

.nav-item.active {
  background: var(--sidebar-item-active);
  color: var(--sidebar-text-active);
  box-shadow: inset 0 0 0 1px rgba(99,102,241,0.25);
}
.nav-item.active .nav-icon { color: var(--brand-primary-light); }

.nav-icon {
  font-size: 16px !important;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: color var(--transition-fast);
}
.nav-label { flex: 1; }
.nav-active-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-primary-light);
  flex-shrink: 0;
  box-shadow: 0 0 6px var(--brand-primary);
}

/* Footer */
.sidebar-footer { padding: 10px; }
.footer-divider {
  height: 1px;
  background: var(--sidebar-border);
  margin-bottom: 10px;
}
.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.user-card:hover { background: var(--sidebar-item-hover); }
.user-avatar, .header-avatar {
  background: var(--brand-gradient) !important;
  color: #fff !important;
  font-weight: 700 !important;
  font-size: 13px !important;
  flex-shrink: 0;
}
.user-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.user-email {
  font-size: 12px;
  font-weight: 500;
  color: var(--sidebar-text-hover);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-role {
  font-size: 11px;
  color: var(--sidebar-text);
}
.logout-icon {
  font-size: 14px;
  color: var(--sidebar-text);
  opacity: 0.6;
  transition: opacity var(--transition-fast);
}
.user-card:hover .logout-icon { opacity: 1; color: #ef4444; }

/* ── Main Area ── */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* Topbar */
.topbar {
  height: 56px;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 10;
  flex-shrink: 0;
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.01em;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.icon-btn {
  width: 34px !important;
  height: 34px !important;
  background: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text-secondary) !important;
  box-shadow: none !important;
}
.icon-btn:hover {
  border-color: var(--brand-primary) !important;
  color: var(--brand-primary) !important;
  background: var(--el-color-primary-light-9) !important;
}
.notif-badge { display: flex; align-items: center; }
.avatar-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 8px 4px 4px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
  transition: all var(--transition-fast);
}
.avatar-trigger:hover {
  border-color: var(--brand-primary);
  background: var(--el-color-primary-light-9);
}
.dropdown-arrow {
  font-size: 12px;
  color: var(--text-muted);
}
.dropdown-user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px 10px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 4px;
}

/* Content */
.content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  animation: fadeIn var(--transition) forwards;
}

/* Page transition */
.page-enter-active { animation: fadeInUp 220ms cubic-bezier(0.4,0,0.2,1) forwards; }
.page-leave-active { animation: fadeIn 120ms cubic-bezier(0.4,0,0.2,1) reverse forwards; }
</style>
