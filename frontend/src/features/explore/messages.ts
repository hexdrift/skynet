// Hebrew UI strings owned by the explore feature slice. Edit directly.

import { TERMS } from "@/shared/lib/terms";

export const exploreMessages = {
  "explore.filter.all": "הכל",
  "explore.filter.run": TERMS.optimizationTypeRun,
  "explore.filter.grid": TERMS.optimizationTypeGrid,
  "explore.filter.aria": "סינון סוג ריצה",
  "explore.filter.no_match": "אין ריצות מסוג זה.",
  "explore.filter.clear": "הצג הכל",
  "explore.empty.title": "המפה עדיין ריקה. ריצות יופיעו כאן אחרי שהמערכת תעבד אותן.",
  "explore.empty.cta": "צרו ריצה ראשונה",
  "explore.detail.task": `ה${TERMS.task}`,
  "explore.detail.model": TERMS.winningModel,
  "explore.detail.optimizer": TERMS.optimizer,
  "explore.detail.score": TERMS.score,
  "explore.detail.close": "סגור",
  "explore.detail.module": "מודול",
  "explore.detail.open_action": "פתח",
  "explore.tooltip.open_hint": "לחצו לפרטים",
  "explore.map.reset": "איפוס תצוגה",
  "explore.map.zoom_in": "התקרב",
  "explore.map.zoom_out": "התרחק",
  "explore.canvas.aria_label": "מפת פיזור של {count} ריצות. השתמשו בעכבר או באצבע להזזה ולקירוב; לחיצה על נקודה פותחת את פרטי הריצה.",
  "explore.granularity.label": "רמת קיבוץ",
  "explore.granularity.aria": "רמת קיבוץ של אשכולות, מ-{p1} ל-{p2} קבוצות",
  "explore.granularity.value": "{p1} קבוצות",
  "explore.picker.subtitle": "גרסאות של אותה משימה",
  "explore.picker.back": "חזרה לרשימה",
  "explore.canvas.variations_hint": "{n} גרסאות — לחצו לבחירה",
} as const;
