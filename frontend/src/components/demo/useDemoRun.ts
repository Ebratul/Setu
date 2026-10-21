"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { demoLogin, getMe } from "@/lib/api/auth";
import {
  demoErrorKind,
  endSandbox,
  getDemoSteps,
  getRun,
  getSummary,
  gotoStep,
  resetRun,
  runScene,
  setLiveAi,
  skipCoolingOff,
  startSandbox,
  withRateRetry,
  type DemoErrorKind,
  type DemoRun,
  type DemoSandbox,
  type DemoScript,
  type DemoSummary,
  type SceneResult,
} from "@/lib/api/demo";

import {
  dwellMs,
  biText,
  flattenScenes,
  indexForStep,
  isDone,
  nextIndex,
  parseStepParam,
  prevIndex,
  type DemoLang,
  type FlatScene,
  type Speed,
} from "./demoModel";

export type RunStatus = "loading" | "ready" | "error" | "ended";
export type Problem = { kind: DemoErrorKind };

type Opts = {
  /** `?step=N` deep link. */
  initialStep: number | null;
  /** `?play=1`, recording mode. */
  autoPlay: boolean;
  lang: DemoLang;
  /** Recording mode: speed fixed at 1x. */
  fixedPace?: boolean;
};

export function useDemoRun({ initialStep, autoPlay, lang, fixedPace = false }: Opts) {
  const [status, setStatus] = useState<RunStatus>("loading");
  const [problem, setProblem] = useState<Problem | null>(null);
  const [script, setScript] = useState<DemoScript | null>(null);
  const [sandbox, setSandbox] = useState<DemoSandbox | null>(null);
  const [run, setRun] = useState<DemoRun | null>(null);
  const [results, setResults] = useState<Record<string, SceneResult>>({});
  const [index, setIndex] = useState(-1);
  const [view, setView] = useState<"scene" | "summary">("scene");
  const [summary, setSummary] = useState<DemoSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState<Speed>(1);
  const [user, setUser] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [rateWait, setRateWait] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const flat = useMemo<FlatScene[]>(() => (script ? flattenScenes(script) : []), [script]);
  const flatRef = useRef(flat);
  const resultsRef = useRef(results);
  const userRef = useRef<string | null>(null);
  const token = useRef(0);
  const started = useRef(false);
  useEffect(() => {
    flatRef.current = flat;
    resultsRef.current = results;
  });

  const apply = useCallback((r: DemoRun) => {
    setRun(r);
    setSandbox(r.sandbox);
    const map: Record<string, SceneResult> = {};
    for (const s of [...r.scenes, ...(r.last ? [r.last] : [])]) map[`${s.n}.${s.k}`] = s;
    resultsRef.current = map;
    setResults(map);
  }, []);

  const fail = useCallback((e: unknown) => {
    const kind = demoErrorKind(e);
    setProblem({ kind });
    setPlaying(false);
    if (kind === "expired" || kind === "required") setStatus("ended");
  }, []);

  const login = useCallback(async (email: string) => {
    if (userRef.current === email) return;
    await demoLogin(email);
    userRef.current = email;
    setUser(email);
  }, []);

  const enter = useCallback(
    async (i: number) => {
      const f = flatRef.current[i];
      if (!f) return;
      const my = ++token.current;
      setBusy(true);
      setProblem(null);
      setView("scene");
      setIndex(i);
      try {
        await login(f.scene.login_as);
        if (my !== token.current) return;
        const stored = resultsRef.current[f.key];
        if (!(stored && isDone(stored) && stored.route)) {
          const r = await withRateRetry(() => runScene(f.n, f.k), undefined, setRateWait);
          if (my !== token.current) return;
          apply(r);
        }
      } catch (e) {
        if (my === token.current) fail(e);
      } finally {
        if (my === token.current) {
          setBusy(false);
          setRateWait(null);
        }
      }
    },
    [apply, fail, login],
  );

  const finished = useMemo(
    () => Boolean(run?.completed) || (flat.length > 0 && flat.every((f) => isDone(results[f.key]))),
    [run, flat, results],
  );

  const showSummary = useCallback(async () => {
    token.current += 1;
    setView("summary");
    setPlaying(false);
    try {
      setSummary(await getSummary());
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const jump = useCallback(
    async (stepN: number) => {
      const idx = indexForStep(flatRef.current, stepN);
      if (idx === null) return;
      const earlierPending = flatRef.current.slice(0, idx).some((f) => !isDone(resultsRef.current[f.key]));
      if (earlierPending) {
        const my = ++token.current;
        setBusy(true);
        setProblem(null);
        setView("scene");
        try {
          const r = await withRateRetry(() => gotoStep(stepN), undefined, setRateWait);
          if (my !== token.current) return;
          apply(r);
        } catch (e) {
          if (my === token.current) {
            fail(e);
            setBusy(false);
          }
          return;
        }
      }
      await enter(idx);
    },
    [apply, enter, fail],
  );

  const next = useCallback(() => {
    if (view === "summary") return;
    if (index < 0) return void enter(0);
    const n = nextIndex(flatRef.current, index);
    if (n !== null) return void enter(n);
    setPlaying(false);
    if (finished) void showSummary();
  }, [enter, finished, index, showSummary, view]);

  const prev = useCallback(() => {
    if (view === "summary") return setView("scene");
    const p = prevIndex(index);
    if (p !== null) void enter(p);
  }, [enter, index, view]);

  const retry = useCallback(() => {
    if (index >= 0) void enter(index);
  }, [enter, index]);

  const reset = useCallback(async () => {
    const my = ++token.current;
    setBusy(true);
    setPlaying(false);
    setProblem(null);
    setSummary(null);
    try {
      const r = await withRateRetry(() => resetRun(), undefined, setRateWait);
      if (my !== token.current) return;
      apply(r);
      userRef.current = null;
      setIndex(-1);
      setReloadKey((k) => k + 1);
    } catch (e) {
      if (my === token.current) fail(e);
      return;
    } finally {
      if (my === token.current) setBusy(false);
    }
    await enter(0);
  }, [apply, enter, fail]);

  const bootstrap = useCallback(
    async (fresh: boolean) => {
      setStatus("loading");
      setProblem(null);
      try {
        const [sc, sb] = await Promise.all([getDemoSteps(), startSandbox(fresh)]);
        setScript(sc);
        setSandbox(sb);
        const f = flattenScenes(sc);
        flatRef.current = f;
        const r = await getRun();
        apply(r);
        try {
          const me = await getMe();
          userRef.current = me.email;
          setUser(me.email);
        } catch {
          userRef.current = null;
        }
        setStatus("ready");
        setIndex(-1);
        setView("scene");
        const step = parseStepParam(initialStep === null ? null : String(initialStep), f);
        if (autoPlay) setPlaying(true);
        if (step !== null) await jump(step);
        else if (autoPlay) await enter(0);
      } catch (e) {
        fail(e);
        setStatus((s) => (s === "ended" ? s : "error"));
      }
    },
    [apply, autoPlay, enter, fail, initialStep, jump],
  );

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void bootstrap(false);
  }, [bootstrap]);

  const newSandbox = useCallback(() => {
    token.current += 1;
    userRef.current = null;
    setUser(null);
    setSummary(null);
    setPlaying(false);
    void bootstrap(true);
  }, [bootstrap]);

  const end = useCallback(async () => {
    token.current += 1;
    setPlaying(false);
    try {
      await endSandbox();
    } catch {
      /* already gone */
    }
    setStatus("ended");
    setProblem(null);
  }, []);

  const toggleLiveAi = useCallback(
    async (enabled: boolean) => {
      try {
        setSandbox(await setLiveAi(enabled));
      } catch (e) {
        fail(e);
      }
    },
    [fail],
  );

  const skipCooling = useCallback(async () => {
    try {
      const r = await skipCoolingOff();
      setNote(r.note);
      setReloadKey((k) => k + 1);
    } catch (e) {
      fail(e);
    }
  }, [fail]);

  const switchRole = useCallback(
    async (email: string) => {
      try {
        userRef.current = null;
        await login(email);
        setReloadKey((k) => k + 1);
      } catch (e) {
        fail(e);
      }
    },
    [fail, login],
  );

  const setSpeed = useCallback((s: Speed) => setSpeedState(fixedPace ? 1 : s), [fixedPace]);
  const reloadFrame = useCallback(() => setReloadKey((k) => k + 1), []);

  const current = index >= 0 ? (flat[index] ?? null) : null;
  const result = current ? (results[current.key] ?? null) : null;

  const nextRef = useRef(next);
  useEffect(() => {
    nextRef.current = next;
  });
  useEffect(() => {
    if (!playing || busy || view !== "scene" || !current || problem) return;
    if (!isDone(result ?? undefined)) return;
    const len =
      biText(current.scene.caption, lang).length + (current.pos === 1 ? biText(current.step.narration, lang).length : 0);
    const id = setTimeout(() => nextRef.current(), dwellMs(len, fixedPace ? 1 : speed));
    return () => clearTimeout(id);
  }, [playing, busy, view, current, result, problem, lang, speed, fixedPace]);

  return {
    status,
    problem,
    script,
    flat,
    sandbox,
    run,
    results,
    index,
    current,
    result,
    view,
    summary,
    busy,
    playing,
    speed: fixedPace ? (1 as Speed) : speed,
    user,
    reloadKey,
    rateWait,
    note,
    finished,
    url: result?.route ?? null,
    setPlaying,
    setSpeed,
    next,
    prev,
    jump,
    retry,
    reset,
    newSandbox,
    end,
    toggleLiveAi,
    skipCooling,
    switchRole,
    reloadFrame,
    showSummary,
    start: () => void enter(0),
    reload: () => void bootstrap(false),
    dismissNote: () => setNote(null),
  };
}
