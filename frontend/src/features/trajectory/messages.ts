// Hebrew UI strings owned by the trajectory feature slice. Edit directly.
// USER REVIEW MARKER: every string here is end-user-visible Hebrew copy.
// Term references go through TERMS.* so the glossary stays the single
// source of truth (e.g. seedCandidate, winningCandidate, paretoFront).

export const trajectoryMessages = {
  "trajectory.panel.title": "עץ המועמדים",
  "trajectory.panel.subtitle": "כל מועמד שאומץ במהלך האופטימיזציה, מהורה לצאצא",

  "trajectory.empty.pre_first_iteration": "המועמד הראשון יופיע כאן בקרוב",
  "trajectory.empty.not_gepa": "המסלול זמין רק באופטימיזציות עם GEPA",
  "trajectory.empty.no_candidates": "לא נוצרו מועמדים בריצה זו",

  "trajectory.live.indicator": "בזמן אמת",
  "trajectory.live.new_candidate": "מועמד חדש התקבל",

  "trajectory.node.seed_label": "התחלה",
  "trajectory.node.winning_label": "מוביל",
  "trajectory.node.generation_label": "דור {gen}",

  "trajectory.detail.prompt_title": "הפרומפט של המועמד",
  "trajectory.detail.per_example_title": "ציון לכל דוגמה",
  "trajectory.detail.discovered_at": "התגלה אחרי {evals} הערכות",
  "trajectory.detail.parent_link": "נגזר מהמועמד {parent}",
  "trajectory.detail.parents_extra_link": "מאוחד גם עם {parents}",
  "trajectory.detail.no_parent": "מועמד התחלתי (ללא הורה)",
  "trajectory.detail.collapse": "הסתרת הפרטים",
  "trajectory.detail.expand": "הצגת הפרטים",

  "trajectory.explainer.candidate": "גרסה של פרומפט שה-GEPA יצר ובחן",
  "trajectory.explainer.parent": "המועמד שממנו צמח המועמד הנוכחי",
  "trajectory.explainer.generation": "כמה דורות עברו מאז ההתחלה",
  "trajectory.explainer.trajectory": "השרשרת של המועמדים שאומצו לאורך הריצה",
  "trajectory.explainer.score": "ממוצע הציון על דוגמאות האימות",

  "trajectory.controls.zoom_in": "הגדלה",
  "trajectory.controls.zoom_out": "הקטנה",
  "trajectory.controls.zoom_reset": "איפוס תצוגה",
  "trajectory.controls.fit": "התאמת תצוגה",

  "trajectory.a11y.tree_label": "עץ המועמדים של האופטימיזציה",
  "trajectory.a11y.node_label": "מועמד {id}, דור {gen}, ציון {score}",
  "trajectory.a11y.live_region": "התקבל מועמד חדש: {id}, ציון {score}",
} as const;

export type TrajectoryMessageKey = keyof typeof trajectoryMessages;
