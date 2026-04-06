import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/LoginView.vue"),
    meta: { guest: true },
  },
  {
    path: "/register",
    name: "Register",
    component: () => import("@/views/RegisterView.vue"),
    meta: { guest: true },
  },
  {
    path: "/",
    component: () => import("@/layouts/AppLayout.vue"),
    meta: { requiresAuth: true },
    children: [
      { path: "", redirect: "/workspace" },
      {
        path: "workspace",
        name: "Workspace",
        component: () => import("@/views/WorkspaceView.vue"),
      },
      {
        path: "knowledge-base",
        name: "KnowledgeBase",
        component: () => import("@/views/KnowledgeBaseView.vue"),
      },
      {
        path: "contents",
        name: "ContentList",
        component: () => import("@/views/ContentListView.vue"),
      },
      {
        path: "contents/:id",
        name: "ContentDetail",
        component: () => import("@/views/ContentDetailView.vue"),
      },
      {
        path: "publish",
        name: "Publish",
        component: () => import("@/views/PublishView.vue"),
      },
      {
        path: "videos",
        name: "VideoProjects",
        component: () => import("@/views/VideoProjectsView.vue"),
      },
      {
        path: "videos/:id",
        name: "VideoDetail",
        component: () => import("@/views/VideoDetailView.vue"),
      },
      {
        path: "settings",
        name: "Settings",
        component: () => import("@/views/SettingsView.vue"),
      },
    ],
  },
  // Catch-all → login
  { path: "/:pathMatch(.*)*", redirect: "/login" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, from, next) => {
  const auth = useAuthStore();
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return next("/login");
  }
  if (to.meta.guest && auth.isAuthenticated) {
    return next("/workspace");
  }
  next();
});

export default router;
