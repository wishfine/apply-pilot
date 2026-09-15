import { defineConfig } from "wxt";

export default defineConfig({
  outDir: "../../dist/extension",
  manifestVersion: 3,
  manifest: {
    name: "ApplyPilot 网申助手",
    description: "在当前已登录的招聘页面中安全、可解释地辅助填写申请表",
    version: "0.1.3",
    permissions: ["activeTab", "scripting", "storage", "sidePanel"],
    optional_permissions: ["tabs"],
    optional_host_permissions: ["http://*/*", "https://*/*"],
    action: { default_title: "打开 ApplyPilot" },
    side_panel: { default_path: "sidepanel.html" },
    options_ui: { page: "options.html", open_in_tab: true },
    commands: {
      "open-sidepanel": {
        suggested_key: { default: "Ctrl+Shift+Y", mac: "Command+Shift+Y" },
        description: "打开 ApplyPilot 侧栏",
      },
    },
  },
});
