export type CodeAssistDefault = "auto" | "manual";
export type SplitModeDefault = "auto" | "manual";
export type TrustModeDefault = "ask" | "auto_safe" | "yolo";

export interface AgentShortcut {
  key: string;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  meta: boolean;
}

export interface UserPrefs {
  advancedMode: boolean;
  wizardCodeAssist: CodeAssistDefault;
  wizardSplitMode: SplitModeDefault;
  agentTrustMode: TrustModeDefault;
  agentShortcut: AgentShortcut;
}

export const PREF_KEYS: Record<keyof UserPrefs, string> = {
  advancedMode: "skynet.prefs.advanced-mode",
  wizardCodeAssist: "skynet.prefs.wizard.code-assist",
  wizardSplitMode: "skynet.prefs.wizard.split-mode",
  agentTrustMode: "skynet.prefs.agent.trust-mode",
  agentShortcut: "skynet.prefs.agent.shortcut",
};

export const DEFAULT_AGENT_SHORTCUT: AgentShortcut = {
  key: "j",
  ctrl: true,
  alt: false,
  shift: false,
  meta: false,
};

export const DEFAULT_PREFS: UserPrefs = {
  advancedMode: false,
  wizardCodeAssist: "auto",
  wizardSplitMode: "auto",
  agentTrustMode: "ask",
  agentShortcut: DEFAULT_AGENT_SHORTCUT,
};

export function readPref<K extends keyof UserPrefs>(key: K): UserPrefs[K] {
  if (typeof window === "undefined") return DEFAULT_PREFS[key];
  try {
    const raw = window.localStorage.getItem(PREF_KEYS[key]);
    if (raw == null) return DEFAULT_PREFS[key];
    return JSON.parse(raw) as UserPrefs[K];
  } catch {
    return DEFAULT_PREFS[key];
  }
}

export function writePref<K extends keyof UserPrefs>(key: K, value: UserPrefs[K]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PREF_KEYS[key], JSON.stringify(value));
  } catch {
    /* noop */
  }
}
