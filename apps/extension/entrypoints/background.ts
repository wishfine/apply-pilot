import { browser } from "wxt/browser";
import { defineBackground } from "wxt/utils/define-background";

export default defineBackground(() => {
  const openPanel = async () => {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (tab?.windowId !== undefined) await browser.sidePanel.open({ windowId: tab.windowId });
  };
  browser.runtime.onInstalled.addListener(() => { void browser.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }); });
  browser.runtime.onStartup.addListener(() => { void browser.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }); });
  browser.commands.onCommand.addListener((command) => { if (command === "open-sidepanel") void openPanel(); });
});
