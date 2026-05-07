import { useEffect, useState, useCallback, FormEvent } from "react";
import { Building2, Users, Mail, Trash2, Crown, Shield, UserMinus, Plus, RefreshCw, Copy, Check, Receipt, AlertCircle } from "lucide-react";
import { Card, Button, Spinner } from "@/components/ui";
import { orgsApi, type Organisation, type OrgMembre, type OrgInvite, type OrgFacture } from "@/api/client";
import toast from "react-hot-toast";

const fmtFCFA = (n: number) => new Intl.NumberFormat("fr-FR").format(Math.round(n));

export const OrganisationPage = () => {
  const [org, setOrg] = useState<Organisation | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"membres" | "invitations" | "facturation" | "settings">("membres");
  const [membres, setMembres] = useState<OrgMembre[]>([]);
  const [invitations, setInvitations] = useState<OrgInvite[]>([]);
  const [factures, setFactures] = useState<OrgFacture[]>([]);

  const charger = useCallback(async () => {
    setLoading(true);
    try {
      const o = await orgsApi.monOrg();
      setOrg(o);
      if (o) {
        const m = await orgsApi.membres(o.id);
        setMembres(m.membres);
      }
    } catch {
      toast.error("Erreur de chargement");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { charger(); }, [charger]);

  useEffect(() => {
    if (!org) return;
    if (tab === "invitations" && (org.mon_role === "owner" || org.mon_role === "admin")) {
      orgsApi.invitations(org.id).then(r => setInvitations(r.invitations)).catch(() => {});
    }
    if (tab === "facturation" && (org.mon_role === "owner" || org.mon_role === "admin")) {
      orgsApi.factures(org.id).then(r => setFactures(r.factures)).catch(() => {});
    }
  }, [tab, org]);

  if (loading) return (
    <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  );

  if (!org) return <CreerOrgForm onCreated={charger} />;

  const isAdmin = org.mon_role === "owner" || org.mon_role === "admin";

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">{org.nom}</h1>
            <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
              <span>Plan {org.plan}</span>
              <span>·</span>
              <span>{fmtFCFA(org.prix_par_siege_fcfa)} {org.devise}/siège/mois</span>
              <span>·</span>
              <span>{membres.length} membre{membres.length > 1 ? "s" : ""} actif{membres.length > 1 ? "s" : ""}</span>
              {org.max_seats && <><span>·</span><span>plafond {org.max_seats}</span></>}
            </div>
          </div>
        </div>
        <RoleBadge role={org.mon_role!} />
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-700">
        {([
          { id: "membres",     label: "Membres",      icon: Users,   adminOnly: false },
          { id: "invitations", label: "Invitations",  icon: Mail,    adminOnly: true  },
          { id: "facturation", label: "Facturation",  icon: Receipt, adminOnly: true  },
          { id: "settings",    label: "Paramètres",   icon: Shield,  adminOnly: true  },
        ] as const).filter(t => !t.adminOnly || isAdmin).map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm border-b-2 transition-colors ${
              tab === t.id ? "border-violet-500 text-white" : "border-transparent text-slate-400 hover:text-slate-200"
            }`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "membres" && (
        <MembresTab org={org} membres={membres} onRefresh={charger} />
      )}
      {tab === "invitations" && isAdmin && (
        <InvitationsTab org={org} invitations={invitations}
          onRefresh={() => orgsApi.invitations(org.id).then(r => setInvitations(r.invitations))} />
      )}
      {tab === "facturation" && isAdmin && (
        <FacturationTab factures={factures} />
      )}
      {tab === "settings" && isAdmin && (
        <SettingsTab org={org} onUpdated={charger} />
      )}
    </div>
  );
};

// ── Sous-composants ─────────────────────────────────────────────────────────

const RoleBadge = ({ role }: { role: string }) => {
  const map: Record<string, { label: string; cls: string; icon: any }> = {
    owner:  { label: "Owner",  cls: "bg-amber-500/20 text-amber-300 border-amber-500/40",  icon: Crown },
    admin:  { label: "Admin",  cls: "bg-blue-500/20 text-blue-300 border-blue-500/40",     icon: Shield },
    member: { label: "Membre", cls: "bg-slate-700/40 text-slate-300 border-slate-600",     icon: Users },
  };
  const r = map[role] || map.member;
  const Icon = r.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border text-xs font-medium ${r.cls}`}>
      <Icon className="w-3.5 h-3.5" /> {r.label}
    </span>
  );
};

const CreerOrgForm = ({ onCreated }: { onCreated: () => void }) => {
  const [nom, setNom] = useState("");
  const [pays, setPays] = useState("CM");
  const [secteur, setSecteur] = useState("");
  const [prix, setPrix] = useState(8000);
  const [domain, setDomain] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (nom.trim().length < 2) return toast.error("Nom trop court");
    setBusy(true);
    try {
      await orgsApi.creer({
        nom, pays, secteur: secteur || undefined,
        prix_par_siege_fcfa: prix,
        domain_auto_join: domain.trim().toLowerCase() || undefined,
      });
      toast.success("Organisation créée");
      onCreated();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec création");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto animate-fade-in">
      <Card className="p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Créer une organisation</h1>
            <p className="text-xs text-slate-400 mt-0.5">Plan Entreprise — facturation par siège</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <Input label="Nom de l'organisation" value={nom} onChange={setNom} required />
          <div className="grid grid-cols-2 gap-3">
            <Input label="Pays (ISO 2)" value={pays} onChange={setPays} maxLength={2} />
            <Input label="Secteur (optionnel)" value={secteur} onChange={setSecteur} />
          </div>
          <div>
            <label className="text-xs uppercase font-semibold text-slate-400 block mb-1">
              Prix par siège (FCFA / mois)
            </label>
            <input type="number" value={prix} min={0} step={500}
              onChange={e => setPrix(parseInt(e.target.value) || 0)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <div>
            <label className="text-xs uppercase font-semibold text-slate-400 block mb-1">
              Domaine email pour auto-join (optionnel — vérification requise après création)
            </label>
            <input value={domain} onChange={e => setDomain(e.target.value)}
              placeholder="entreprise.com"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" />
            <p className="text-xs text-slate-500 mt-1">
              Tout email se terminant par ce domaine sera rattaché automatiquement comme membre.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-xs text-blue-200 flex gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              Vous serez l'<strong>owner</strong>. Vous pouvez inviter des membres ensuite,
              changer leur rôle et gérer la facturation.
            </p>
          </div>

          <Button type="submit" loading={busy} icon={<Plus className="w-4 h-4" />} className="w-full">
            Créer mon organisation
          </Button>
        </form>
      </Card>
    </div>
  );
};

const MembresTab = ({ org, membres, onRefresh }: { org: Organisation; membres: OrgMembre[]; onRefresh: () => void }) => {
  const isAdmin = org.mon_role === "owner" || org.mon_role === "admin";
  const handleChangeRole = async (m: OrgMembre, nouveau: "admin" | "member") => {
    try {
      await orgsApi.changerRole(org.id, m.user_id, nouveau);
      toast.success(`${m.nom || m.email} → ${nouveau}`);
      onRefresh();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec");
    }
  };
  const handleRetirer = async (m: OrgMembre) => {
    if (!confirm(`Retirer ${m.nom || m.email} de l'organisation ?`)) return;
    try {
      await orgsApi.retirerMembre(org.id, m.user_id);
      toast.success("Membre retiré");
      onRefresh();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec");
    }
  };

  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
          <tr>
            <th className="text-left px-4 py-3 font-semibold">Membre</th>
            <th className="text-left px-4 py-3 font-semibold">Rôle</th>
            <th className="text-left px-4 py-3 font-semibold">Rejoint</th>
            <th className="text-right px-4 py-3 font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {membres.map(m => (
            <tr key={m.id} className="hover:bg-slate-800/30">
              <td className="px-4 py-3">
                <div className="font-medium text-white">{m.nom || m.username}</div>
                <div className="text-xs text-slate-500">{m.email}</div>
              </td>
              <td className="px-4 py-3"><RoleBadge role={m.role} /></td>
              <td className="px-4 py-3 text-xs text-slate-400">
                {new Date(m.joined_at).toLocaleDateString()}
              </td>
              <td className="px-4 py-3 text-right">
                {isAdmin && m.role !== "owner" && (
                  <div className="flex gap-2 justify-end">
                    {m.role === "member" ? (
                      <button onClick={() => handleChangeRole(m, "admin")}
                        className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-300 hover:bg-blue-500/20">
                        Promouvoir admin
                      </button>
                    ) : (
                      <button onClick={() => handleChangeRole(m, "member")}
                        className="text-xs px-2 py-1 rounded bg-slate-700/40 text-slate-300 hover:bg-slate-700">
                        Rétrograder
                      </button>
                    )}
                    <button onClick={() => handleRetirer(m)}
                      className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-300 hover:bg-red-500/20"
                      title="Retirer">
                      <UserMinus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
};

const InvitationsTab = ({ org, invitations, onRefresh }: { org: Organisation; invitations: OrgInvite[]; onRefresh: () => void }) => {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "admin">("member");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const inviter = async (e: FormEvent) => {
    e.preventDefault();
    if (!email.includes("@")) return toast.error("Email invalide");
    setBusy(true);
    try {
      const inv = await orgsApi.inviter(org.id, email, role);
      const url = `${window.location.origin}/orgs/invites/${inv.token}`;
      navigator.clipboard?.writeText(url).catch(() => {});
      toast.success("Invitation créée — lien copié");
      setEmail("");
      onRefresh();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec");
    } finally {
      setBusy(false);
    }
  };

  const revoquer = async (inv: OrgInvite) => {
    if (!confirm(`Révoquer l'invitation de ${inv.email} ?`)) return;
    try {
      await orgsApi.revoquerInvite(org.id, inv.id);
      toast.success("Invitation révoquée");
      onRefresh();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec");
    }
  };

  const copyLink = (token?: string) => {
    if (!token) return;
    const url = `${window.location.origin}/orgs/invites/${token}`;
    navigator.clipboard?.writeText(url);
    setCopied(token); setTimeout(() => setCopied(null), 2000);
    toast.success("Lien copié");
  };

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <h2 className="text-sm font-semibold text-white mb-3">Inviter un membre</h2>
        <form onSubmit={inviter} className="flex gap-2 flex-wrap">
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            placeholder="email@entreprise.com"
            className="flex-1 min-w-64 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" />
          <select value={role} onChange={e => setRole(e.target.value as any)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white">
            <option value="member">Membre</option>
            <option value="admin">Admin</option>
          </select>
          <Button type="submit" loading={busy} icon={<Mail className="w-4 h-4" />}>Inviter</Button>
        </form>
      </Card>

      <Card className="overflow-hidden">
        {invitations.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">Aucune invitation</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Email</th>
                <th className="text-left px-4 py-3 font-semibold">Rôle</th>
                <th className="text-left px-4 py-3 font-semibold">Statut</th>
                <th className="text-left px-4 py-3 font-semibold">Expire</th>
                <th className="text-right px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {invitations.map(i => (
                <tr key={i.id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-3 text-white">{i.email}</td>
                  <td className="px-4 py-3"><RoleBadge role={i.role} /></td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      i.statut === "en_attente" ? "bg-amber-500/10 text-amber-300" :
                      i.statut === "accepte"    ? "bg-emerald-500/10 text-emerald-300" :
                      "bg-slate-700/40 text-slate-400"
                    }`}>{i.statut}</span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(i.expires_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {i.statut === "en_attente" && (
                      <div className="flex gap-2 justify-end">
                        {i.token && (
                          <button onClick={() => copyLink(i.token)}
                            className="text-xs px-2 py-1 rounded bg-slate-700/40 text-slate-300 hover:bg-slate-700"
                            title="Copier lien">
                            {copied === i.token ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        )}
                        <button onClick={() => revoquer(i)}
                          className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-300 hover:bg-red-500/20"
                          title="Révoquer">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
};

const FacturationTab = ({ factures }: { factures: OrgFacture[] }) => (
  <Card className="overflow-hidden">
    {factures.length === 0 ? (
      <p className="p-6 text-center text-sm text-slate-500">
        Aucune facture pour le moment. La première sera générée à la fin du mois en cours.
      </p>
    ) : (
      <table className="w-full text-sm">
        <thead className="bg-slate-800/50 text-slate-400 text-xs uppercase">
          <tr>
            <th className="text-left px-4 py-3 font-semibold">Période</th>
            <th className="text-right px-4 py-3 font-semibold">Sièges max</th>
            <th className="text-right px-4 py-3 font-semibold">Prix unit.</th>
            <th className="text-right px-4 py-3 font-semibold">Montant</th>
            <th className="text-left px-4 py-3 font-semibold">Statut</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {factures.map(f => (
            <tr key={f.id} className="hover:bg-slate-800/30">
              <td className="px-4 py-3 text-white">
                {new Date(f.period_debut).toLocaleDateString()} → {new Date(f.period_fin).toLocaleDateString()}
              </td>
              <td className="px-4 py-3 text-right">{f.sieges_max}</td>
              <td className="px-4 py-3 text-right">{fmtFCFA(f.prix_unitaire_fcfa)} {f.devise}</td>
              <td className="px-4 py-3 text-right font-semibold text-white">{fmtFCFA(f.montant_total_fcfa)} {f.devise}</td>
              <td className="px-4 py-3">
                <span className={`text-xs px-2 py-0.5 rounded ${
                  f.statut === "paye" ? "bg-emerald-500/10 text-emerald-300" :
                  f.statut === "a_payer" ? "bg-amber-500/10 text-amber-300" :
                  "bg-slate-700/40 text-slate-400"
                }`}>{f.statut}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </Card>
);

const SettingsTab = ({ org, onUpdated }: { org: Organisation; onUpdated: () => void }) => {
  const [nom, setNom] = useState(org.nom);
  const [pays, setPays] = useState(org.pays || "");
  const [secteur, setSecteur] = useState(org.secteur || "");
  const [domain, setDomain] = useState(org.domain_auto_join || "");
  const [busy, setBusy] = useState(false);

  const sauvegarder = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await orgsApi.update(org.id, {
        nom, pays: pays || undefined, secteur: secteur || undefined,
        domain_auto_join: domain.trim().toLowerCase() || undefined,
      });
      toast.success("Organisation mise à jour");
      onUpdated();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <form onSubmit={sauvegarder} className="space-y-4">
        <Input label="Nom" value={nom} onChange={setNom} />
        <div className="grid grid-cols-2 gap-3">
          <Input label="Pays (ISO 2)" value={pays} onChange={setPays} maxLength={2} />
          <Input label="Secteur" value={secteur} onChange={setSecteur} />
        </div>
        <div>
          <label className="text-xs uppercase font-semibold text-slate-400 block mb-1">
            Domaine email auto-join {org.domain_verifie ? <span className="text-emerald-400">· vérifié</span> : <span className="text-amber-400">· à vérifier</span>}
          </label>
          <input value={domain} onChange={e => setDomain(e.target.value)}
            placeholder="entreprise.com"
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" />
        </div>
        <Button type="submit" loading={busy} icon={<RefreshCw className="w-4 h-4" />}>
          Enregistrer
        </Button>
      </form>
    </Card>
  );
};

const Input = ({ label, value, onChange, ...rest }: any) => (
  <div>
    <label className="text-xs uppercase font-semibold text-slate-400 block mb-1">{label}</label>
    <input value={value} onChange={e => onChange(e.target.value)} {...rest}
      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white" />
  </div>
);
