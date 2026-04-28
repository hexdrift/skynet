export { UserPrefsProvider, useUserPrefs } from "./hooks/use-user-prefs";
export { SettingsModalProvider, useSettingsModal } from "./hooks/use-settings-modal";
export { SettingsModal } from "./components/SettingsModal";
export { SettingsTrigger } from "./components/SettingsTrigger";
export {
  readPref,
  writePref,
  DEFAULT_PREFS,
  DEFAULT_AGENT_SHORTCUT,
  PREF_KEYS,
} from "./lib/prefs";
export type {
  UserPrefs,
  CodeAssistDefault,
  SplitModeDefault,
  TrustModeDefault,
  AgentShortcut,
} from "./lib/prefs";
export { formatShortcut, matchShortcut, recordShortcut } from "./lib/shortcuts";
