"use client";

import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { apiErrorText } from "@/lib/api/formErrors";
import { inviteMember, listMembers, removeMember, type Member, type MemberRole } from "@/lib/api/members";
import { useShellUser } from "@/lib/MeContext";
import { useApi } from "@/lib/useApi";

const ROLES: MemberRole[] = ["OWNER", "FINANCE", "VIEWER"];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function TeamPage() {
  const t = useT();
  const shellMe = useShellUser();
  const fetched = useApi((s) => getMe(s), "me", shellMe === undefined);
  const me = shellMe ?? fetched.data;
  const partyId = me?.party_id ?? null;
  const members = useApi((s) => listMembers(partyId ?? "", s), `members|${partyId}`, partyId !== null);

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<MemberRole>("FINANCE");
  const [fieldErr, setFieldErr] = useState<{ email?: string; name?: string }>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const mine = members.data?.items.find((m) => m.user_id === me?.id);
  const canWrite = mine === undefined || mine.member_role === "OWNER";

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    if (!partyId) return;
    const errs: { email?: string; name?: string } = {};
    if (!EMAIL.test(email.trim())) errs.email = t("team.v.email");
    if (name.trim().length < 2 || name.trim().length > 120) errs.name = t("onb.v.length", { min: 2, max: 120 });
    setFieldErr(errs);
    if (errs.email || errs.name) return;
    setBusy(true);
    setFormError(null);
    setNotice(null);
    try {
      const m = await inviteMember(partyId, { email: email.trim(), display_name: name.trim(), member_role: role });
      setNotice(t("team.invited", { email: m.email }));
      setEmail("");
      setName("");
      members.reload();
    } catch (err) {
      setFormError(apiErrorText(err, t, "team.err"));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove() {
    if (!partyId || !removing) return;
    setRemoveBusy(true);
    setRemoveError(null);
    try {
      await removeMember(partyId, removing.user_id);
      setNotice(t("team.removed", { email: removing.email }));
      setRemoving(null);
      members.reload();
    } catch (err) {
      setRemoveError(apiErrorText(err, t, "team.err"));
    } finally {
      setRemoveBusy(false);
    }
  }

  const columns: Column<Member>[] = [
    {
      id: "person",
      header: t("team.col.person"),
      sortValue: (m) => m.display_name.toLowerCase(),
      cell: (m) => (
        <span className="font-semibold text-ink">
          {m.display_name}
          <span className="block text-xs font-normal break-all text-muted">{m.email}</span>
        </span>
      ),
    },
    { id: "role", header: t("team.col.role"), cell: (m) => <Badge tone={m.member_role === "OWNER" ? "info" : "neutral"}>{t(`team.role.${m.member_role}`)}</Badge> },
    {
      id: "signed",
      header: t("team.col.signedIn"),
      cell: (m) => (
        <Badge tone={m.signed_in_once ? "success" : "warning"}>
          {m.signed_in_once ? t("team.signedIn") : t("team.notSignedIn")}
        </Badge>
      ),
    },
  ];
  if (canWrite) {
    columns.push({
      id: "remove",
      header: t("team.col.action"),
      cell: (m) => (
        <Button
          size="sm"
          variant="secondary"
          aria-label={t("team.removeLabel", { name: m.display_name })}
          onClick={() => {
            setRemoveError(null);
            setRemoving(m);
          }}
        >
          {t("team.remove")}
        </Button>
      ),
    });
  }

  let body;
  if (me && !partyId) {
    body = <EmptyState title={t("team.noParty")} />;
  } else if (members.error) {
    body = <QueryError error={members.error} onRetry={members.reload} />;
  } else if (!members.data) {
    body = <Skeleton className="h-48" />;
  } else {
    body = <DataTable caption={t("team.title")} columns={columns} rows={members.data.items} rowKey={(m) => m.user_id} />;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-ink">{t("team.title")}</h1>
        <p className="text-muted">{t("team.intro")}</p>
      </header>

      <div aria-live="polite">{notice ? <Alert tone="success">{notice}</Alert> : null}</div>

      <section aria-labelledby="team-list-h" className="space-y-3" aria-busy={members.loading}>
        <h2 id="team-list-h" className="text-lg font-bold text-ink">
          {t("team.members")}
        </h2>
        {body}
      </section>

      {canWrite && partyId && members.data ? (
        <section aria-labelledby="team-invite-h" className="max-w-xl space-y-3">
          <h2 id="team-invite-h" className="text-lg font-bold text-ink">
            {t("team.invite")}
          </h2>
          <Alert tone="info">{t("team.noEmail")}</Alert>
          <form onSubmit={(e) => void onInvite(e)} noValidate className="space-y-4">
            {formError ? (
              <p role="alert" className="text-sm font-medium text-danger">
                {formError}
              </p>
            ) : null}
            <FormField id="team-email" label={t("team.f.email")} error={fieldErr.email}>
              {(aria) => (
                <input {...aria} type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
              )}
            </FormField>
            <FormField id="team-name" label={t("team.f.name")} error={fieldErr.name}>
              {(aria) => (
                <input {...aria} type="text" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
              )}
            </FormField>
            <FormField id="team-role" label={t("team.f.role")} hint={t(`team.roleHelp.${role}`)}>
              {(aria) => (
                <select {...aria} value={role} onChange={(e) => setRole(e.target.value as MemberRole)} className={inputClass}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`team.role.${r}`)}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <Button type="submit" loading={busy}>
              {busy ? t("team.inviting") : t("team.inviteSubmit")}
            </Button>
          </form>
        </section>
      ) : null}

      {removing ? (
        <ConfirmDialog
          title={t("team.removeTitle")}
          confirmLabel={t("team.remove")}
          busy={removeBusy}
          error={removeError}
          onConfirm={() => void onRemove()}
          onClose={() => !removeBusy && setRemoving(null)}
        >
          <p>{t("team.removeBody", { name: removing.display_name, email: removing.email })}</p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
