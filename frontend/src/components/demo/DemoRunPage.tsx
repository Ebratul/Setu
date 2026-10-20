"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ButtonLink } from "@/components/landing/ButtonLink";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useLang, useT } from "@/i18n";
import { demoLogin } from "@/lib/api/auth";
import { useNow } from "@/lib/usePoll";

import { Controls } from "./Controls";
import { biText, formatCountdown, parseMode, ROLES, roleOfEmail, toDemoLang } from "./demoModel";
import { presenterAction } from "./keys";
import { NarrationPanel, TagChip } from "./NarrationPanel";
import { PhonePanel } from "./PhonePanel";
import { Scorecard } from "./Scorecard";
import { fitScale } from "./spotlight";
import { browserSpeaker } from "./speech";
import { Stage } from "./Stage";
import { StepList } from "./StepList";
import { SummaryPanel } from "./SummaryPanel";
import { ToolsPanel } from "./ToolsPanel";
import { useDemoRun } from "./useDemoRun";
import { useReadAloud } from "./useReadAloud";

type Tab = "app" | "story" | "score";
type RoleId = (typeof ROLES)[number]["id"] | "";

function FullPage({ title, body, children }: { title: string; body?: string; children?: React.ReactNode }) {
  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-lg flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-extrabold text-ink">{title}</h1>
      {body ? (
        <p role="status" className="text-base text-muted">
          {body}
        </p>
      ) : null}
      <div className="flex flex-wrap justify-center gap-2">{children}</div>
    </main>
  );
}

export function DemoRunPage() {
  const t = useT();
  const router = useRouter();
  const sp = useSearchParams();
  const { lang, setLang } = useLang();
  const dl = toDemoLang(lang);
  const mode = parseMode(sp.get("mode"));
  const presenter = mode === "presenter";
  const record = mode === "record";
  const stepRaw = sp.get("step");
  const initialStep = stepRaw && /^\d+$/.test(stepRaw) ? Number(stepRaw) : null;
  const langParam = sp.get("lang");

  const run = useDemoRun({ initialStep, autoPlay: sp.get("play") === "1" || record, lang: dl, fixedPace: record });
  const { on: readAloud, setOn: setReadAloud, supported: speechSupported } = useReadAloud();
  const speaker = useMemo(() => browserSpeaker(), []);

  const [tab, setTab] = useState<Tab>("app");
  const [confirm, setConfirm] = useState<"reset" | "end" | null>(null);
  const [blackout, setBlackout] = useState(false);
  const [notes, setNotes] = useState(false);
  const [frameEl, setFrameEl] = useState<HTMLIFrameElement | null>(null);
  const [mountedAt] = useState(() => Date.now());
  const now = useNow(1000, true);
  const [viewport, setViewport] = useState({ width: 1920, height: 1080 });

  useEffect(() => {
    if (langParam === "bn" || langParam === "en") setLang(langParam);
  }, [langParam, setLang]);

  useEffect(() => {
    if (!record) return;
    const on = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    on();
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, [record]);

  const { current, result, view, busy } = run;
  const speakText = current ? [current.pos === 1 ? biText(current.step.narration, dl) : "", biText(current.scene.caption, dl)].filter(Boolean).join(". ") : "";
  useEffect(() => {
    if (!readAloud || view !== "scene" || !current || busy) return;
    speaker.speak(speakText, dl);
    return () => speaker.cancel();
  }, [readAloud, view, current, busy, speakText, dl, speaker]);
  useEffect(() => () => speaker.cancel(), [speaker]);

  const latest = useRef({ run, confirm });
  useEffect(() => {
    latest.current = { run, confirm };
  });
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen?.();
    else void document.documentElement.requestFullscreen?.();
  };
  const fullscreenRef = useRef(toggleFullscreen);
  useEffect(() => {
    fullscreenRef.current = toggleFullscreen;
  });
  useEffect(() => {
    if (!presenter) return;
    const onKey = (e: KeyboardEvent) => {
      const a = presenterAction(e);
      if (!a || latest.current.confirm) return;
      e.preventDefault();
      const r = latest.current.run;
      if (a === "next") r.next();
      else if (a === "prev") r.prev();
      else if (a === "toggle") {
        if (r.index < 0) {
          r.setPlaying(true);
          r.start();
        } else r.setPlaying(!r.playing);
      } else if (a === "reset") setConfirm("reset");
      else if (a === "blackout") setBlackout((b) => !b);
      else if (a === "notes") setNotes((n) => !n);
      else fullscreenRef.current();
    };
    window.addEventListener("keydown", onKey);
    let doc: Document | null = null;
    const attach = () => {
      try {
        doc?.removeEventListener("keydown", onKey);
        doc = frameEl?.contentDocument ?? null;
        doc?.addEventListener("keydown", onKey);
      } catch {
        doc = null;
      }
    };
    attach();
    frameEl?.addEventListener("load", attach);
    return () => {
      window.removeEventListener("keydown", onKey);
      frameEl?.removeEventListener("load", attach);
      try {
        doc?.removeEventListener("keydown", onKey);
      } catch {
        /* frame gone */
      }
    };
  }, [presenter, frameEl]);

  const explore = useCallback(async () => {
    try {
      await demoLogin(ROLES[0].email);
    } catch {
      /* the buyer cookie may already be valid */
    }
    router.push("/app");
  }, [router]);

  if (run.status === "loading") return <FullPage title={t("demo.title")} body={t("demo.starting")} />;
  if (run.status === "ended" || run.status === "error") {
    const kind = run.problem?.kind;
    const key = run.status === "ended" && !kind ? "ended" : (kind ?? "network");
    return (
      <FullPage title={t("demo.title")} body={t(`demo.err.${key}`, { s: 5 })}>
        <Button onClick={run.status === "error" && kind !== "capacity" ? run.reload : run.newSandbox}>
          {run.status === "error" && kind !== "capacity" ? t("demo.err.retry") : t("demo.err.newSandbox")}
        </Button>
        <ButtonLink href="/demo" variant="secondary">
          {t("demo.summary.hub")}
        </ButtonLink>
      </FullPage>
    );
  }

  const last = run.flat.length - 1;
  const started = run.index >= 0;
  const frameKey = `${current?.key ?? "none"}:${run.reloadKey}:${lang}`;
  const stageEl = (
    <Stage
      url={view === "summary" ? (run.url ?? null) : run.url}
      frameKey={frameKey}
      highlight={current?.scene.highlight}
      caption={current ? biText(current.scene.caption, dl) : ""}
      busy={busy}
      spotlightOn={view === "scene" && !run.problem}
      frameRef={setFrameEl}
      empty={
        <div className="max-w-sm space-y-2">
          <p className="text-lg font-bold text-ink">{t("demo.stage.emptyTitle")}</p>
          <p className="text-sm text-muted">{t("demo.stage.emptyBody")}</p>
        </div>
      }
    />
  );

  if (record) {
    const scale = fitScale(viewport);
    return (
      <div className="fixed inset-0 overflow-hidden bg-ink cursor-none" data-testid="record-root">
        <h1 className="sr-only">{t("demo.title")}</h1>
        <main
          id="main"
          className="absolute top-1/2 left-1/2 overflow-hidden"
          style={{ width: 1920, height: 1080, transform: `translate(-50%, -50%) scale(${scale})` }}
          data-testid="record-stage"
        >
          {stageEl}
          {current ? (
            <div aria-live="polite" className="absolute bottom-10 left-10 flex max-w-[60%] items-center gap-4 rounded-2xl bg-surface px-6 py-4 shadow-card-hover">
              <TagChip tag={current.step.tag} />
              <p className="text-3xl font-extrabold text-ink">{biText(current.step.title, dl)}</p>
            </div>
          ) : null}
          <p className="absolute top-6 right-6 rounded-full border border-warning bg-warning-soft px-4 py-1.5 text-lg font-semibold text-warning">{t("demo.banner")}</p>
        </main>
      </div>
    );
  }

  const onTogglePlay = () => {
    if (view === "summary") return;
    if (!started) {
      run.setPlaying(true);
      run.start();
    } else run.setPlaying(!run.playing);
  };
  const controls = (
    <Controls
      started={started}
      busy={busy}
      playing={run.playing}
      speed={run.speed}
      canPrev={view === "summary" || run.index > 0}
      canNext={view === "scene" && started && (run.index < last || run.finished)}
      showSpeed
      onStart={run.start}
      onPrev={run.prev}
      onNext={run.next}
      onTogglePlay={onTogglePlay}
      onSpeed={run.setSpeed}
    />
  );
  const effTab: Tab = view === "summary" && tab === "app" ? "story" : tab;
  const show = (id: Tab) => (effTab === id ? "" : "hidden md:block");
  const remaining = run.sandbox ? new Date(run.sandbox.expires_at).getTime() - now : null;
  const role: RoleId = roleOfEmail(run.user) ?? "";
  const elapsed = formatCountdown(now - mountedAt);

  return (
    <div className={`flex h-dvh flex-col overflow-hidden bg-surface-alt ${presenter ? "presenter" : ""}`}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
      >
        {t("shell.skip")}
      </a>
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface px-3 py-2">
        <h1 className="text-base font-extrabold text-ink">
          <Link href="/demo" className="rounded focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
            {t("demo.title")}
          </Link>
        </h1>
        <p data-testid="sim-banner" className="rounded-full border border-warning bg-warning-soft px-3 py-1 text-xs font-semibold text-warning">
          {t("demo.banner")}
        </p>
        {current ? (
          <p className="text-sm font-semibold text-ink" data-testid="progress">
            {t("demo.progress", { step: current.n, pos: current.pos, count: current.count })}
            <span className="text-muted"> · {t("demo.progressOf", { n: run.index + 1, total: run.flat.length })}</span>
          </p>
        ) : null}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {remaining !== null ? (
            <p role="timer" aria-label={t("demo.expires")} className="text-xs font-semibold text-muted">
              {t("demo.expires")}: {formatCountdown(remaining)}
            </p>
          ) : null}
          {presenter ? (
            <>
              <p role="timer" aria-label={t("demo.presenter.timer")} className="text-sm font-bold text-ink" data-testid="timer">
                ⏱ {elapsed}
              </p>
              <Button size="sm" variant="secondary" onClick={toggleFullscreen}>
                {t("demo.presenter.fullscreen")}
              </Button>
              <Button size="sm" variant="secondary" aria-pressed={notes} onClick={() => setNotes((n) => !n)}>
                {t("demo.presenter.notes")}
              </Button>
            </>
          ) : null}
          <SegmentedControl<RoleId>
            legend={t("demo.role.label")}
            value={role}
            onChange={(v) => {
              const r = ROLES.find((x) => x.id === v);
              if (r) void run.switchRole(r.email);
            }}
            options={ROLES.map((r) => ({ value: r.id, label: t(`demo.role.${r.id}`) }))}
          />
          <LanguageToggle />
        </div>
      </header>

      <div role="tablist" aria-label={t("demo.tabs.label")} className="flex border-b border-line bg-surface md:hidden">
        {(["app", "story", "score"] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`demo-tab-${id}`}
            aria-selected={effTab === id}
            aria-controls={`demo-panel-${id}`}
            onClick={() => setTab(id)}
            className={`min-h-11 flex-1 border-b-2 px-2 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
              effTab === id ? "border-brand-700 text-brand-text" : "border-transparent text-muted"
            }`}
          >
            {t(`demo.tabs.${id}`)}
          </button>
        ))}
      </div>

      <main id="main" className="flex min-h-0 flex-1 flex-col pb-36 md:flex-row md:pb-0">
        <section
          id="demo-panel-app"
          role="region"
          aria-label={t("demo.stage.label")}
          className={`min-h-[60dvh] flex-1 md:min-h-0 ${effTab === "app" ? "" : "hidden md:block"}`}
        >
          {stageEl}
        </section>

        <aside
          aria-label={t("demo.panel.label")}
          className={`min-h-0 w-full shrink-0 overflow-y-auto border-line bg-surface md:w-[26rem] md:border-l ${presenter ? "[zoom:1.15] " : ""}`}
        >
          <div className="hidden border-b border-line p-3 md:block">{controls}</div>
          {presenter && notes && current ? (
            <section aria-labelledby="demo-notes-h" data-testid="notes" className="border-b border-line bg-accent-400/10 p-4">
              <h2 id="demo-notes-h" className="text-sm font-bold text-ink">
                {t("demo.presenter.notesTitle")}
              </h2>
              <p className="mt-1 text-sm text-ink">{biText(current.step.notes, dl)}</p>
            </section>
          ) : null}
          <div id="demo-panel-story" role="region" aria-labelledby="demo-tab-story" className={`space-y-5 p-4 ${show("story")}`}>
            {view === "summary" ? (
              <SummaryPanel summary={run.summary} onBack={run.prev} onExplore={() => void explore()} />
            ) : (
              <NarrationPanel current={current} result={result} busy={busy} problem={run.problem} rateWait={run.rateWait} onRetry={run.retry} onNext={run.next} />
            )}
            {run.finished && view === "scene" ? (
              <Button variant="accent" onClick={() => void run.showSummary()}>
                {t("demo.summary.show")}
              </Button>
            ) : null}
            {run.script ? (
              <StepList steps={run.script.steps} results={run.results} currentStep={current?.n ?? null} disabled={busy} onJump={(n) => void run.jump(n)} />
            ) : null}
            <PhonePanel active />
            <ToolsPanel
              sandbox={run.sandbox}
              busy={busy}
              readAloud={readAloud}
              speechSupported={speechSupported}
              note={run.note}
              onLiveAi={(v) => void run.toggleLiveAi(v)}
              onReadAloud={setReadAloud}
              onSkipCooling={() => void run.skipCooling()}
              onReset={() => setConfirm("reset")}
              onEnd={() => setConfirm("end")}
              onReloadFrame={run.reloadFrame}
            />
          </div>
          <div id="demo-panel-score" role="region" aria-labelledby="demo-tab-score" className={`p-4 ${show("score")}`}>
            <Scorecard items={run.run?.scorecard ?? []} />
          </div>
        </aside>
      </main>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface p-2 shadow-card-hover md:hidden" data-testid="mobile-controls">
        {controls}
      </div>

      {confirm === "reset" ? (
        <ConfirmDialog
          title={t("demo.reset.title")}
          confirmLabel={t("demo.tools.reset")}
          onClose={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null);
            void run.reset();
          }}
        >
          <p>{t("demo.reset.body")}</p>
        </ConfirmDialog>
      ) : null}
      {confirm === "end" ? (
        <ConfirmDialog
          title={t("demo.end.title")}
          confirmLabel={t("demo.tools.end")}
          onClose={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null);
            void run.end();
          }}
        >
          <p>{t("demo.end.body")}</p>
        </ConfirmDialog>
      ) : null}
      {blackout ? (
        <button
          type="button"
          onClick={() => setBlackout(false)}
          aria-label={t("demo.presenter.blackout")}
          className="fixed inset-0 z-60 cursor-pointer bg-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        />
      ) : null}
    </div>
  );
}
