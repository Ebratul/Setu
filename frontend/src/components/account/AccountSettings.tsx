"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import {
  exportAccount,
  getAccount,
  patchAccount,
  requestDeletion,
  totpDisable,
  totpRegenerate,
} from "@/lib/api/account";
import { apiErrorText } from "@/lib/api/formErrors";
import type { Lang } from "@/lib/api/onboarding";
import { getAuthClient } from "@/lib/auth/client";
import { signOutEverywhere } from "@/lib/auth/flow";
import { isValidTotp } from "@/lib/onboarding/validate";
import { downloadHref } from "@/lib/qr";
import { useApi } from "@/lib/useApi";

import { RecoveryCodes } from "./RecoveryCodes";
import { SessionsList } from "./SessionsList";
import { TotpEnroll } from "./TotpEnroll";

const LANGS: Lang[] = ["en", "bn", "zh"];

type CodeAction = "disable" | "regenerate";

function CodeDialog({ action, onDone, onClose }: { action: CodeAction; onDone: (codes: string[] | null) => void; onClose: () => void }) {
  const t = useT();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (!isValidTotp(code)) {
      setError(t("ob.v.code6"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (action === "disable") {
        await totpDisable(code.trim());
        onDone(null);
      } else {
        onDone((await totpRegenerate(code.trim())).recovery_codes);
      }
    } catch (e) {
      setError(apiErrorText(e, t, "tp.err"));
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog title={t(`as.2fa.${action}.title`)} confirmLabel={t(`as.2fa.${action}.confirm`)} busy={busy} error={error} confirmDisabled={code.length !== 6} onConfirm={() => void confirm()} onClose={onClose}>
      <p>{t(`as.2fa.${action}.body`)}</p>
      <FormField id="as-2fa-code" label={`${t("tp.code")} *`}>
        {(aria) => (
          <input {...aria} aria-required type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className={`${inputClass} min-h-11 max-w-48 font-mono tracking-widest`} />
        )}
      </FormField>
    </ConfirmDialog>
  );
}

export function AccountSettings() {
  const t = useT();
  const router = useRouter();
  const toast = useToast();
  const { lang, setLang } = useLang();
  const q = useApi((s) => getAccount(s), "account");
  const [enrolling, setEnrolling] = useState(false);
  const [codeAction, setCodeAction] = useState<CodeAction | null>(null);
  const [newCodes, setNewCodes] = useState<string[] | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const a = q.data;
  const [google, setGoogle] = useState(false);
  useEffect(() => {
    let live = true;
    const list = getAuthClient().listAccounts() as Promise<{ data?: { providerId?: string; provider?: string }[] | null }>;
    list.then(
      (r) => live && setGoogle((r.data ?? []).some((x) => (x.providerId ?? x.provider) === "google")),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, []);

  async function leave() {
    await signOutEverywhere();
    router.replace("/login");
  }

  async function onLanguage(next: Lang) {
    setLang(next);
    try {
      await patchAccount({ language: next });
      toast(t("as.saved"));
    } catch (e) {
      toast(apiErrorText(e, t, "ob.err"), "danger");
    }
  }

  async function onExport() {
    setBusy(true);
    try {
      const data = await exportAccount();
      downloadHref(`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(data, null, 2))}`, "setu-my-data.json");
    } catch (e) {
      toast(apiErrorText(e, t, "ob.err"), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    setBusy(true);
    setError(null);
    try {
      await requestDeletion();
      await leave();
    } catch (e) {
      setError(apiErrorText(e, t, "ob.err"));
      setBusy(false);
    }
  }

  if (q.error) return <QueryError error={q.error} onRetry={q.reload} />;
  if (!a) return <Skeleton className="h-64" />;
  const isAdmin = a.role === "ADMIN";

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold text-ink">{t("as.title")}</h1>
        <p className="text-muted">{t("as.lead")}</p>
      </header>

      <Card as="section" labelledBy="as-profile-h" className="space-y-3">
        <h2 id="as-profile-h" className="text-lg font-bold text-ink">
          {t("as.profile")}
        </h2>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">{t("ob.f.full_name")}</dt>
            <dd className="font-medium text-ink">{a.display_name ?? "-"}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("auth.signIn.email")}</dt>
            <dd className="font-medium break-all text-ink">{a.email}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("as.role")}</dt>
            <dd className="font-medium text-ink">{t(`role.${a.role}`)}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("ob.f.mobile")}</dt>
            <dd className="font-mono font-medium text-ink">{a.mobile_masked ?? "-"}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("as.linked")}</dt>
            <dd className="font-medium text-ink">{google ? t("as.linked.google") : t("as.linked.email")}</dd>
          </div>
          {a.terms_version ? (
            <div>
              <dt className="text-muted">{t("as.terms")}</dt>
              <dd className="font-medium text-ink">{a.terms_version}</dd>
            </div>
          ) : null}
        </dl>
        <FormField id="as-language" label={t("ob.f.language")}>
          {(aria) => (
            <select {...aria} value={lang} onChange={(e) => void onLanguage(e.target.value as Lang)} className={`${inputClass} min-h-11 max-w-xs`}>
              {LANGS.map((l) => (
                <option key={l} value={l}>
                  {t(`ob.lang.${l}`)}
                </option>
              ))}
            </select>
          )}
        </FormField>
      </Card>

      <Card as="section" labelledBy="as-2fa-h" className="space-y-3">
        <h2 id="as-2fa-h" className="text-lg font-bold text-ink">
          {t("as.2fa")}
        </h2>
        {newCodes ? (
          <RecoveryCodes codes={newCodes} onConfirmed={() => setNewCodes(null)} />
        ) : enrolling ? (
          <TotpEnroll
            onComplete={() => {
              setEnrolling(false);
              q.reload();
            }}
            onCancel={() => setEnrolling(false)}
          />
        ) : a.mfa_enabled ? (
          <>
            <Alert tone="success">{t("ob.totp.on")}</Alert>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setCodeAction("regenerate")}>
                {t("as.2fa.regenerate")}
              </Button>
              <Button variant="danger" onClick={() => setCodeAction("disable")} disabled={isAdmin}>
                {t("as.2fa.disable")}
              </Button>
            </div>
            {isAdmin ? <p className="text-xs text-muted">{t("as.2fa.adminLocked")}</p> : null}
          </>
        ) : (
          <>
            <p className="text-sm text-muted">{t("ob.totp.optional")}</p>
            <Button onClick={() => setEnrolling(true)}>{t("ob.totp.setup")}</Button>
          </>
        )}
      </Card>

      <Card as="section" labelledBy="as-sessions-h" className="space-y-3">
        <h2 id="as-sessions-h" className="text-lg font-bold text-ink">
          {t("as.sessions")}
        </h2>
        <SessionsList onSignedOutEverywhere={() => void leave()} />
      </Card>

      <Card as="section" labelledBy="as-data-h" className="space-y-3">
        <h2 id="as-data-h" className="text-lg font-bold text-ink">
          {t("as.data")}
        </h2>
        <p className="text-sm text-muted">{t("as.data.body")}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => void onExport()} loading={busy && !deleting}>
            {t("as.export")}
          </Button>
          <Button variant="danger" onClick={() => setDeleting(true)}>
            {t("as.delete")}
          </Button>
        </div>
      </Card>

      {codeAction ? (
        <CodeDialog
          action={codeAction}
          onClose={() => setCodeAction(null)}
          onDone={(codes) => {
            setCodeAction(null);
            if (codes) setNewCodes(codes);
            else {
              toast(t("as.2fa.disabled"));
              q.reload();
            }
          }}
        />
      ) : null}
      {deleting ? (
        <ConfirmDialog title={t("as.delete.title")} confirmLabel={t("as.delete.confirm")} busy={busy} error={error} onConfirm={() => void onDelete()} onClose={() => !busy && setDeleting(false)}>
          <p>{t("as.delete.body")}</p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
