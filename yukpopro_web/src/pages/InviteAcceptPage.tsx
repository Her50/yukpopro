import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Building2, CheckCircle, XCircle } from "lucide-react";
import { Card, Button, Spinner } from "@/components/ui";
import { orgsApi } from "@/api/client";
import toast from "react-hot-toast";

export const InviteAcceptPage = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [details, setDetails] = useState<any>(null);

  useEffect(() => {
    if (!token) return;
    orgsApi.detailInvite(token)
      .then(setDetails)
      .catch((err) => setErreur(err?.response?.data?.detail || "Invitation introuvable"))
      .finally(() => setLoading(false));
  }, [token]);

  const accepter = async () => {
    if (!token) return;
    setBusy(true);
    try {
      const r = await orgsApi.accepterInvite(token);
      toast.success(`Bienvenue dans l'organisation (${r.role})`);
      navigate("/organisation");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Échec acceptation");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>;

  if (erreur) return (
    <div className="p-6 max-w-md mx-auto">
      <Card className="p-6 space-y-3 text-center">
        <XCircle className="w-12 h-12 text-red-400 mx-auto" />
        <h1 className="text-lg font-semibold text-white">Invitation invalide</h1>
        <p className="text-sm text-slate-400">{erreur}</p>
        <Button onClick={() => navigate("/")} variant="ghost">Retour</Button>
      </Card>
    </div>
  );

  if (!details) return null;
  const { invitation, organisation } = details;
  const expiree = invitation.statut !== "en_attente";

  return (
    <div className="p-6 max-w-md mx-auto">
      <Card className="p-6 space-y-5">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">Invitation</h1>
            <p className="text-xs text-slate-400">à rejoindre une organisation</p>
          </div>
        </div>

        <div className="bg-slate-800/40 rounded-lg p-4 space-y-2">
          <div>
            <div className="text-xs text-slate-500">Organisation</div>
            <div className="font-semibold text-white">{organisation.nom}</div>
          </div>
          {organisation.secteur && (
            <div>
              <div className="text-xs text-slate-500">Secteur</div>
              <div className="text-sm text-white">{organisation.secteur}</div>
            </div>
          )}
          <div className="flex justify-between text-sm pt-1 border-t border-slate-700">
            <span className="text-slate-400">Rôle proposé</span>
            <span className="font-medium text-white capitalize">{invitation.role}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Email destinataire</span>
            <span className="font-medium text-white">{invitation.email}</span>
          </div>
        </div>

        {expiree ? (
          <div className="text-center text-sm text-amber-300">
            Invitation {invitation.statut}.
          </div>
        ) : (
          <Button onClick={accepter} loading={busy} icon={<CheckCircle className="w-4 h-4" />}
            className="w-full">
            Accepter et rejoindre
          </Button>
        )}
        <p className="text-xs text-center text-slate-500">
          Vous devez être connecté avec l'email <strong>{invitation.email}</strong> pour accepter.
        </p>
      </Card>
    </div>
  );
};
