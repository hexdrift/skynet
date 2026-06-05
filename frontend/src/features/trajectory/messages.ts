// Hebrew UI strings owned by the trajectory feature slice. Edit directly.
// USER REVIEW MARKER: every string here is end-user-visible Hebrew copy.
// Term references go through TERMS.* so the glossary stays the single
// source of truth (e.g. winningCandidate).

export const trajectoryMessages = {
  "trajectory.panel.title": "עץ המועמדים",

  "trajectory.live.new_candidate": "התקבל מועמד חדש",

  "trajectory.node.winning_label": "מוביל",

  "trajectory.detail.pareto_title": "דוגמאות האימות",
  "trajectory.detail.pareto_title.explain": "כל ריבוע מייצג דוגמת אימות. ירוק = תשובה נכונה, אדום = תשובה שגויה. לחצו כדי לפתוח את הדוגמה.",
  "trajectory.detail.pareto_example_label": "דוגמה {id}, ציון {score}",
  "trajectory.detail.pareto_passed": "{count} עברו מתוך {total}",
  "trajectory.detail.diff_unchanged": "ללא שינוי לעומת ההורה",

  "trajectory.drawer.section.minibatch": "משוב על ה-mini-batch",
  "trajectory.drawer.section.minibatch.explain": "mini-batch = תת-קבוצה קטנה של דוגמאות שעליה ההצעה נבחנה לפני שהוחלט אם לאמץ אותה.",
  "trajectory.drawer.toggle.aria": "תצוגת הפרומפט",
  "trajectory.drawer.toggle.prompt": "פרומפט",
  "trajectory.drawer.toggle.diff": "השוואה",
  "trajectory.drawer.rejected.prompt_title": "הפרומפט שהוצע ונדחה",
  "trajectory.drawer.rejected.prompt_title.explain": "ההבדל בין פרומפט ההורה לבין הפרומפט שמודל הרפלקציה יצר ושנדחה. שורות בירוק נוספו, שורות באדום הוסרו.",
  "trajectory.drawer.rejected.prompt_unavailable": "טקסט ההצעה לא נשמר בריצה זו",

  "trajectory.pareto.cell_detail_pending": "תוכן הדוגמה עדיין לא נטען מהשרת",
  "trajectory.pareto.cell.inputs_label": "קלט",
  "trajectory.pareto.cell.outputs_label": "תשובה מצופה",
  "trajectory.pareto.cell.prediction_label": "תשובת המועמד",
  "trajectory.pareto.cell.prediction_unavailable": "התשובה לא נמצאה",
  "trajectory.pareto.cell.inputs_label.explain": "הנתונים שהוצגו למועמד מתוך דוגמת האימות.",
  "trajectory.pareto.cell.prediction_label.explain": "התשובה שהמועמד הציע על הקלט הזה במהלך הריצה על דוגמאות האימות.",
  "trajectory.pareto.cell.outputs_label.explain": "התשובה הנכונה לפי דוגמת האימות; הציון נקבע לפי ההשוואה אליה.",
  "trajectory.pareto.cell.details_label": "פרטים נוספים",
  "trajectory.pareto.cell.allowed_tools_label": "כלים זמינים",
  "trajectory.minibatch.no_data": "אין משוב mini-batch זמין בשלב זה",
  "trajectory.minibatch.score_label": "ציון",
  "trajectory.minibatch.score_label.explain": "הציון שפונקציית המדידה החזירה על הדוגמה הזו בלבד. ערך גבוה יותר = תשובה טובה יותר לפי פונקציית המדידה. ערכי ביניים מציינים זיכוי חלקי.",
  "trajectory.minibatch.question_label": "השאלה",
  "trajectory.minibatch.question_label.explain": "הקלט שהוצג למועמד מתוך הדוגמה הזו.",
  "trajectory.minibatch.prediction_label": "תשובת המועמד",
  "trajectory.minibatch.prediction_label.explain": "התשובה שהמועמד הציע על הקלט.",
  "trajectory.minibatch.feedback_label": "משוב הרפלקציה",
  "trajectory.minibatch.feedback_label.explain": "המשוב שמודל הרפלקציה ניסח לאחר ההערכה — מסביר למה התשובה נכונה או שגויה.",
  "trajectory.minibatch.pass_label": "דוגמה שעברה אימות",
  "trajectory.minibatch.fail_label": "דוגמה שלא עברה אימות",

  "trajectory.ghost.legend": "הצעות שנדחו",

  "trajectory.node.header.accepted_title": "מועמד {id}",
  "trajectory.node.header.rejected_title": "הצעה שנדחתה",
  "trajectory.node.header.label.iteration": "סבב",
  "trajectory.node.header.label.score_valset": "ציון האימות",
  "trajectory.node.header.label.score_minibatch": "ציון ההצעה שנדחתה",
  "trajectory.node.header.label.parent_score": "ציון ההורה",
  "trajectory.node.header.sub.examples": "{n} דוגמאות",

  "trajectory.node.section.prompt": "הפרומפט",
  "trajectory.node.section.prompt.explain": "הוראות הסוכן עבור המועמד הזה — הטקסט שמודל הרפלקציה משנה כדי לשפר את הביצועים.",
  "trajectory.prompt.react.tools": "תיאורי הכלים ({n})",
  "trajectory.prompt.react.tools.explain": "התיאור של כל כלי ושל הארגומנטים שלו, כפי שעודכנו באופטימיזציה. דפדפו בין הכלים כדי לראות את הפירוט המלא.",
  "trajectory.prompt.react.tools_carousel_aria": "דפדוף בין תיאורי הכלים",
  "trajectory.prompt.react.tools.view_aria": "תצוגת תיאורי הכלים",
  "trajectory.prompt.react.tools.view_plain": "תיאור",
  "trajectory.prompt.react.tools.view_compare": "השוואה",
  "trajectory.prompt.react.tool.added": "נוסף",
  "trajectory.prompt.react.tool.removed": "הוסר",
  "trajectory.prompt.react.tool.changed": "שונה",
  "trajectory.json.empty_value": "ריק",
  "trajectory.chat.recorded_label": "שיחה מתועדת",
  "trajectory.chat.recorded_label.explain": "תיעוד שמור של חילופי ההודעות שהוצגו למועמד — לקריאה בלבד, לא שיחה פעילה.",
  "trajectory.chat.recorded_count": "{n} הודעות",
  "trajectory.node.section.score_detail.valset": "ציונים לכל דוגמת אימות",

  "trajectory.explainer.trajectory": "רצף המועמדים שאומצו לאורך הריצה",

  "trajectory.controls.zoom_in": "הגדילו",
  "trajectory.controls.zoom_out": "הקטינו",
  "trajectory.controls.zoom_reset": "אפסו תצוגה",
  "trajectory.controls.fullscreen_enter": "עברו לתצוגה מלאה",
  "trajectory.controls.fullscreen_exit": "צאו מתצוגה מלאה",

  "trajectory.scrubber.label": "סינון לפי דור",
  "trajectory.scrubber.live": "חי",
  "trajectory.scrubber.generation_value": "דור {gen}",

  "trajectory.a11y.tree_label": "עץ המועמדים של האופטימיזציה",
  "trajectory.a11y.node_label": "מועמד {id}, דור {gen}, ציון {score}",
} as const;
