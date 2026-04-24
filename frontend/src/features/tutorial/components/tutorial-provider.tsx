"use client";

import * as React from "react";
import { useReducer, useEffect, useCallback, useRef, createContext, useContext } from "react";
import type { TutorialTrack } from "@/features/tutorial/lib/steps";
import { getTrack } from "@/features/tutorial/lib/steps";

/* ═══════════════════════════════════════════════════════════
   State Shape
   ═══════════════════════════════════════════════════════════ */

export interface TutorialState {
  activeTrack: TutorialTrack | null;
  currentStepIndex: number;
  isVisible: boolean;
  isMenuOpen: boolean;
  isAutoPlaying: boolean;
  completedTracks: Set<TutorialTrack>;
}

type TutorialAction =
  | { type: "START_TRACK"; track: TutorialTrack }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "GO_TO_STEP"; index: number }
  | { type: "EXIT_TUTORIAL" }
  | { type: "COMPLETE_TRACK" }
  | { type: "OPEN_MENU" }
  | { type: "CLOSE_MENU" }
  | { type: "RESET_ALL" }
  | { type: "TOGGLE_AUTO_PLAY" }
  | { type: "SET_AUTO_PLAY"; value: boolean }
  | { type: "LOAD_STATE"; state: Partial<TutorialState> };

function tutorialReducer(state: TutorialState, action: TutorialAction): TutorialState {
  switch (action.type) {
    case "START_TRACK":
      return {
        ...state,
        activeTrack: action.track,
        currentStepIndex: 0,
        isVisible: true,
        isMenuOpen: false,
      };
    case "NEXT_STEP": {
      if (!state.activeTrack) return state;
      const track = getTrack(state.activeTrack);
      if (!track) return state;
      const nextIndex = state.currentStepIndex + 1;
      if (nextIndex >= track.steps.length) {
        return {
          ...state,
          isVisible: false,
          completedTracks: new Set([...state.completedTracks, state.activeTrack]),
        };
      }
      return { ...state, currentStepIndex: nextIndex };
    }
    case "PREV_STEP":
      return state.activeTrack
        ? { ...state, currentStepIndex: Math.max(0, state.currentStepIndex - 1) }
        : state;
    case "GO_TO_STEP": {
      if (!state.activeTrack) return state;
      const t = getTrack(state.activeTrack);
      if (!t) return state;
      return {
        ...state,
        currentStepIndex: Math.max(0, Math.min(action.index, t.steps.length - 1)),
      };
    }
    case "EXIT_TUTORIAL":
      return { ...state, isVisible: false, isMenuOpen: false };
    case "COMPLETE_TRACK":
      return state.activeTrack
        ? {
            ...state,
            isVisible: false,
            completedTracks: new Set([...state.completedTracks, state.activeTrack]),
          }
        : state;
    case "OPEN_MENU":
      return { ...state, isMenuOpen: true, isVisible: false };
    case "CLOSE_MENU":
      return { ...state, isMenuOpen: false };
    case "TOGGLE_AUTO_PLAY":
      return { ...state, isAutoPlaying: !state.isAutoPlaying };
    case "SET_AUTO_PLAY":
      return { ...state, isAutoPlaying: action.value };
    case "RESET_ALL":
      return {
        activeTrack: null,
        currentStepIndex: 0,
        isVisible: false,
        isMenuOpen: false,
        isAutoPlaying: false,
        completedTracks: new Set(),
      };
    case "LOAD_STATE":
      return {
        ...state,
        ...action.state,
        completedTracks: new Set(action.state.completedTracks || []),
      };
    default:
      return state;
  }
}

const initialState: TutorialState = {
  activeTrack: null,
  currentStepIndex: 0,
  isVisible: false,
  isMenuOpen: false,
  isAutoPlaying: false,
  completedTracks: new Set(),
};

const STORAGE_KEY = "skynet-tutorial-state";

/* ═══════════════════════════════════════════════════════════
   Context
   ═══════════════════════════════════════════════════════════ */

interface TutorialContextValue {
  state: TutorialState;
  currentStep: ReturnType<typeof getTrack> extends { steps: (infer S)[] } | undefined
    ? S | undefined
    : never;
  startTrack: (track: TutorialTrack) => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (index: number) => void;
  exitTutorial: () => void;
  completeTrack: () => void;
  openMenu: () => void;
  closeMenu: () => void;
  resetAll: () => void;
  toggleAutoPlay: () => void;
}

const TutorialContext = createContext<TutorialContextValue | null>(null);

export function TutorialProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(tutorialReducer, initialState);

  // Restore full state on mount (survives page navigation)
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        dispatch({
          type: "LOAD_STATE",
          state: {
            completedTracks: new Set(parsed.completedTracks || []),
            activeTrack: parsed.activeTrack || null,
            currentStepIndex: parsed.currentStepIndex || 0,
            isVisible: parsed.isVisible || false,
          },
        });
      }
    } catch {
      /* ignore */
    }

    // Auto-start tutorial in auto-play mode via URL param
    const params = new URLSearchParams(window.location.search);
    if (params.get("tutorial") === "autoplay") {
      setTimeout(() => {
        dispatch({ type: "SET_AUTO_PLAY", value: true });
        dispatch({ type: "START_TRACK", track: "deep-dive" as TutorialTrack });
      }, 1000);
    }
  }, []);

  // Persist full state on every change
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          completedTracks: Array.from(state.completedTracks),
          activeTrack: state.activeTrack,
          currentStepIndex: state.currentStepIndex,
          isVisible: state.isVisible,
        }),
      );
    } catch {
      /* ignore */
    }
  }, [state.completedTracks, state.activeTrack, state.currentStepIndex, state.isVisible]);

  const startTrack = useCallback(
    (track: TutorialTrack) => dispatch({ type: "START_TRACK", track }),
    [],
  );
  const nextStep = useCallback(() => dispatch({ type: "NEXT_STEP" }), []);
  const prevStep = useCallback(() => dispatch({ type: "PREV_STEP" }), []);
  const goToStep = useCallback((index: number) => dispatch({ type: "GO_TO_STEP", index }), []);
  const exitTutorial = useCallback(() => dispatch({ type: "EXIT_TUTORIAL" }), []);
  const completeTrack = useCallback(() => dispatch({ type: "COMPLETE_TRACK" }), []);
  const openMenu = useCallback(() => {
    if (window.location.pathname !== "/") {
      // Pre-save tutorial state so it starts after navigation
      try {
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            completedTracks: Array.from(state.completedTracks),
            activeTrack: "deep-dive",
            currentStepIndex: 0,
            isVisible: true,
          }),
        );
      } catch {
        /* ignore */
      }
      window.location.href = "/";
    } else {
      dispatch({ type: "START_TRACK", track: "deep-dive" as TutorialTrack });
    }
  }, [state.completedTracks]);
  const closeMenu = useCallback(() => dispatch({ type: "CLOSE_MENU" }), []);
  const resetAll = useCallback(() => {
    dispatch({ type: "RESET_ALL" });
    localStorage.removeItem(STORAGE_KEY);
  }, []);
  const toggleAutoPlay = useCallback(() => dispatch({ type: "TOGGLE_AUTO_PLAY" }), []);

  // Notify listeners (e.g. dashboard demo overlay) when tutorial closes
  const prevVisible = useRef(state.isVisible);
  useEffect(() => {
    if (prevVisible.current && !state.isVisible) {
      window.dispatchEvent(new Event("tutorial-exited"));
    }
    prevVisible.current = state.isVisible;
  }, [state.isVisible]);

  const currentStep = state.activeTrack
    ? getTrack(state.activeTrack)?.steps[state.currentStepIndex]
    : undefined;

  return (
    <TutorialContext.Provider
      value={{
        state,
        currentStep,
        startTrack,
        nextStep,
        prevStep,
        goToStep,
        exitTutorial,
        completeTrack,
        openMenu,
        closeMenu,
        resetAll,
        toggleAutoPlay,
      }}
    >
      {children}
    </TutorialContext.Provider>
  );
}

export function useTutorialContext() {
  const context = useContext(TutorialContext);
  if (!context) {
    throw new Error("useTutorialContext must be used within TutorialProvider");
  }
  return context;
}
