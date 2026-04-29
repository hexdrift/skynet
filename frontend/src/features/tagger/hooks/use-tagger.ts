"use client";

import { useState, useCallback, useMemo } from "react";
import type { DataRow, Annotation, TaggerConfig, AnnotationMode } from "../lib/types";

function isTagged(ann: Annotation, mode: AnnotationMode): boolean {
  if (ann === undefined || ann === null) return false;
  if (mode === "multiclass") return Array.isArray(ann) && ann.length > 0;
  return typeof ann === "string" && ann !== "";
}

export function useTagger() {
  const [phase, setPhase] = useState<"setup" | "annotating">("setup");
  const [config, setConfig] = useState<TaggerConfig | null>(null);
  const [data, setData] = useState<DataRow[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [annotations, setAnnotations] = useState<Record<string, Annotation>>({});
  const [currentIndex, setCurrentIndex] = useState(0);

  const startAnnotating = useCallback((cfg: TaggerConfig, rows: DataRow[], cols: string[]) => {
    setConfig(cfg);
    setData(rows);
    setColumns(cols);
    setCurrentIndex(0);
    setAnnotations({});
    setPhase("annotating");
  }, []);

  const backToSetup = useCallback(() => {
    setConfig(null);
    setData([]);
    setColumns([]);
    setAnnotations({});
    setCurrentIndex(0);
    setPhase("setup");
  }, []);

  const navigate = useCallback(
    (dir: 1 | -1) => {
      (document.activeElement as HTMLElement)?.blur();
      setCurrentIndex((i) => {
        const next = i + dir;
        if (next < 0 || next >= data.length) return i;
        return next;
      });
    },
    [data.length],
  );

  const goTo = useCallback(
    (idx: number) => {
      (document.activeElement as HTMLElement)?.blur();
      if (idx >= 0 && idx < data.length) setCurrentIndex(idx);
    },
    [data.length],
  );

  const jumpToUntagged = useCallback(() => {
    if (!config) return;
    for (let i = 0; i < data.length; i++) {
      if (!isTagged(annotations[String(data[i]!.id)], config.mode)) {
        setCurrentIndex(i);
        return;
      }
    }
  }, [data, annotations, config]);

  const annotate = useCallback((id: string, value: Annotation) => {
    setAnnotations((prev) => {
      const next = { ...prev };
      if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) {
        delete next[id];
      } else {
        next[id] = value;
      }
      return next;
    });
  }, []);

  const toggleBinary = useCallback((id: string, value: "yes" | "no") => {
    (document.activeElement as HTMLElement)?.blur();
    setAnnotations((prev) => {
      const next = { ...prev };
      if (next[id] === value) {
        delete next[id];
      } else {
        next[id] = value;
      }
      return next;
    });
  }, []);

  const toggleCategory = useCallback((id: string, catId: string) => {
    (document.activeElement as HTMLElement)?.blur();
    setAnnotations((prev) => {
      const next = { ...prev };
      const current = Array.isArray(next[id]) ? [...(next[id] as string[])] : [];
      const idx = current.indexOf(catId);
      if (idx >= 0) current.splice(idx, 1);
      else current.push(catId);
      if (current.length === 0) delete next[id];
      else next[id] = current;
      return next;
    });
  }, []);

  const setFreetext = useCallback((id: string, text: string) => {
    setAnnotations((prev) => {
      const next = { ...prev };
      if (text.trim()) next[id] = text.trim();
      else delete next[id];
      return next;
    });
  }, []);

  const taggedCount = useMemo(
    () =>
      config ? data.filter((d) => isTagged(annotations[String(d.id)], config.mode)).length : 0,
    [config, data, annotations],
  );

  return {
    phase,
    config,
    data,
    columns,
    annotations,
    currentIndex,
    taggedCount,
    startAnnotating,
    backToSetup,
    navigate,
    goTo,
    jumpToUntagged,
    annotate,
    toggleBinary,
    toggleCategory,
    setFreetext,
  };
}
