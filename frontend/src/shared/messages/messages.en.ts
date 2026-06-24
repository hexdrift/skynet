// English UI strings for the shared slice. Edit directly; keys missing here fall
// back to the Hebrew slice via msg(), so partial translations are safe.

import type { sharedMessages } from "./messages";

export const sharedMessagesEn: Partial<Record<keyof typeof sharedMessages, string>> = {
  "shared.language.switch_aria": "Choose interface language",
};
