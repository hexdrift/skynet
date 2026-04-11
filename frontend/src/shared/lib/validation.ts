/**
 * Shared validation functions
 * Provides validation for job names, code, datasets, and model configurations
 * All error messages in Hebrew matching existing wording
 */

import { FORM_CONSTRAINTS } from "../constants";

export const validators = {
  jobName: (name: string): string | null => {
    if (!name || name.trim().length === 0) {
      return "שם העבודה חובה";
    }
    if (name.length > FORM_CONSTRAINTS.MAX_JOB_NAME_LENGTH) {
      return `שם העבודה לא יכול להיות ארוך מ-${FORM_CONSTRAINTS.MAX_JOB_NAME_LENGTH} תווים`;
    }
    return null;
  },

  code: (code: string, type: 'signature' | 'metric'): string | null => {
    if (!code || code.trim().length === 0) {
      return type === 'signature' ? "חתימת מודול חובה" : "קוד מטריקה חובה";
    }

    // Basic Python syntax check
    const lines = code.split('\n');
    const indentationIssue = lines.some((line, i) => {
      if (i === 0) return false;
      const leadingSpaces = line.match(/^(\s*)/)?.[1]?.length ?? 0;
      return leadingSpaces % 4 !== 0 && line.trim().length > 0;
    });

    if (indentationIssue) {
      return "קוד פייתון חייב להשתמש ב-4 רווחים להזחה";
    }

    // Check for required elements
    if (type === 'signature') {
      if (!code.includes('->')) {
        return "חתימת המודול חייבת לכלול -> לסוג החזרה";
      }
    }

    if (type === 'metric') {
      if (!code.includes('def ') && !code.includes('lambda ')) {
        return "קוד המטריקה חייב להגדיר פונקציה";
      }
    }

    return null;
  },

  dataset: (file: File | null): string | null => {
    if (!file) {
      return "יש להעלות קובץ דאטאסט";
    }

    const validExtensions = ['.csv', '.xlsx', '.xls', '.json'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

    if (!validExtensions.includes(fileExtension)) {
      return `סוג קובץ לא נתמך. השתמש ב: ${validExtensions.join(', ')}`;
    }

    const maxSize = 50 * 1024 * 1024; // 50MB
    if (file.size > maxSize) {
      return "גודל הקובץ חורג מ-50MB";
    }

    return null;
  },

  modelConfig: (config: { model?: string; temperature?: number; max_tokens?: number }): string | null => {
    if (!config.model) {
      return "יש לבחור מודל";
    }

    if (config.temperature !== undefined) {
      if (config.temperature < 0 || config.temperature > 2) {
        return "טמפרטורה חייבת להיות בין 0 ל-2";
      }
    }

    if (config.max_tokens !== undefined) {
      if (config.max_tokens < 1 || config.max_tokens > 32000) {
        return "מקסימום טוקנים חייב להיות בין 1 ל-32000";
      }
    }

    return null;
  },
};
