/**
 * Decorative sample artifacts for the login backdrop.
 *
 * These are FAKE, illustrative task labels — never real user data — used purely
 * as the scattered "product halo" behind the sign-in panel. Each is a finished
 * task shown by its name, so the halo reads like a wall of Skynet's own
 * completed runs without exposing any numbers. Positions are hand-placed around
 * the edges to keep a clean centre. The full halo shows from the `md` breakpoint
 * up; below it there isn't room to scatter cards around a near-full-width panel,
 * so a curated few carry `mobilePos` to frame the login on small portrait
 * screens, and the rest drop away (see LoginHalo).
 */

export interface HaloCard {
  title: string;
  pos: { top?: string; bottom?: string; left?: string; right?: string };
  rot: number;
  /** When set, the card also frames the login on small portrait screens, placed here. */
  mobilePos?: { top?: string; bottom?: string; left?: string; right?: string };
}

export const HALO_CARDS: HaloCard[] = [
  // Top band — front row
  { title: "סיווג כוונות", pos: { top: "-3%", left: "1%" }, rot: -5, mobilePos: { top: "6%", left: "4%" } },
  { title: "סיכום פגישה", pos: { top: "-4%", left: "15%" }, rot: 3 },
  { title: "תיוג מסמכים", pos: { top: "-2%", left: "29%" }, rot: -4 },
  { title: "זיהוי שפה", pos: { top: "-3%", left: "43%" }, rot: 4, mobilePos: { top: "13%", right: "5%" } },
  { title: "סינון תוכן", pos: { top: "-2%", left: "57%" }, rot: -3 },
  { title: "שכתוב שאילתה", pos: { top: "-4%", left: "71%" }, rot: 5 },
  { title: "קישור ישויות", pos: { top: "-3%", right: "2%" }, rot: -5 },

  // Top band — middle row
  { title: "חילוץ ישויות", pos: { top: "9%", left: "7%" }, rot: 4 },
  { title: "ניתוח סנטימנט", pos: { top: "11%", left: "26%" }, rot: -3, mobilePos: { top: "20%", left: "22%" } },
  { title: "חילוץ מילות מפתח", pos: { top: "9%", left: "45%" }, rot: 5 },
  { title: "זיהוי ספאם", pos: { top: "11%", left: "64%" }, rot: -4 },
  { title: "תיקון דקדוק", pos: { top: "9%", left: "81%" }, rot: 3 },

  // Top band — back row (centre chip dropped so it never sits behind the wordmark)
  { title: "חילוץ ציטוטים", pos: { top: "19%", left: "6%" }, rot: -4 },
  { title: "תיוג חלקי דיבר", pos: { top: "19%", left: "80%" }, rot: -3 },

  // Left wing — outer column
  { title: "דירוג רלוונטיות", pos: { top: "30%", left: "-3%" }, rot: 5 },
  { title: "מענה לשאלות", pos: { top: "44%", left: "-3%" }, rot: 6 },
  { title: "התאמת מוצרים", pos: { top: "58%", left: "-2%" }, rot: 4 },
  { title: "זיהוי סתירות", pos: { top: "70%", left: "-3%" }, rot: -3 },

  // Left wing — inner column
  { title: "ניקוד איכות", pos: { top: "37%", left: "7%" }, rot: -4 },
  { title: "חילוץ נושאים", pos: { top: "64%", left: "7%" }, rot: -3 },

  // Right wing — outer column
  { title: "שימוש בכלים", pos: { top: "30%", right: "2%" }, rot: -5 },
  { title: "דירוג תשובות", pos: { top: "44%", right: "3%" }, rot: -6 },
  { title: "זיהוי הונאה", pos: { top: "58%", right: "4%" }, rot: -4 },
  { title: "חשיבה מתמטית", pos: { top: "70%", right: "3%" }, rot: 5 },

  // Right wing — inner column
  { title: "מענה מבוסס מקורות", pos: { top: "37%", right: "9%" }, rot: 4 },
  { title: "בדיקת עובדות", pos: { top: "64%", right: "9%" }, rot: 5, mobilePos: { bottom: "20%", right: "20%" } },

  // Bottom band — back row (centre chip dropped so it never sits behind the login card)
  { title: "הרחבת שאילתה", pos: { bottom: "19%", left: "6%" }, rot: 4 },
  { title: "חילוץ JSON", pos: { bottom: "19%", left: "80%" }, rot: 4, mobilePos: { bottom: "6%", right: "4%" } },

  // Bottom band — middle row
  { title: "חילוץ מאפייני מוצר", pos: { bottom: "10%", left: "9%" }, rot: -4 },
  { title: "חילוץ יחסים", pos: { bottom: "11%", left: "25%" }, rot: 4 },
  { title: "חילוץ פרטי קשר", pos: { bottom: "9%", left: "41%" }, rot: -5 },
  { title: "המרה ל-SQL", pos: { bottom: "11%", left: "57%" }, rot: 3 },
  { title: "זיהוי שפה פוגענית", pos: { bottom: "9%", left: "72%" }, rot: -4 },
  { title: "סיכום מסמך", pos: { bottom: "11%", left: "85%" }, rot: 4, mobilePos: { bottom: "13%", left: "5%" } },

  // Bottom band — front row
  { title: "חילוץ תאריכים", pos: { bottom: "-3%", left: "7%" }, rot: 4 },
  { title: "סיווג קטגוריות", pos: { bottom: "2%", left: "23%" }, rot: 5 },
  { title: "זיהוי כוונת רכישה", pos: { bottom: "-2%", left: "40%" }, rot: -3 },
  { title: "אחזור רב-שלבי", pos: { bottom: "3%", left: "57%" }, rot: 4 },
  { title: "סיווג פניות", pos: { bottom: "-3%", left: "73%" }, rot: 5 },
  { title: "ניתוב פניות", pos: { bottom: "-2%", right: "4%" }, rot: 5 },
];
