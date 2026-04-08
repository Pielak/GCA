import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Users, UserPlus, Mail, RefreshCw, Trash2, ShieldCheck,
  ShieldOff, Clock, CheckCircle2, AlertTriangle, X,
} from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";
import { HelpIcon } from "@/components/HelpIcon";

interface Member {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  invite_pending: boolean;
  invite_expired: boolean;
  invite_expires_at: string | null;
  last_login_at: string | null;
  joined_at: string;
}

const ROLES = [
  { value: "project_manager", label: "GP" },
  { value: "tech_lead",       label: "Tech Lead" },
  { value: "dev_senior",      label: "Dev Sênior" },
  { value: "dev_pleno",       label: "Dev Pleno" },
  { value: "qa_engineer",     label: "QA Engineer" },
  { value: "compliance",      label: "Compliance" },
  { value: "security",        label: "Segurança" },
  { value: "scrum_master",    label: "Scrum Master" },
  { value: "legal",           label: "Jurídico" },
  { value: "stakeholder",     label: "Stakeholder" },
];

function MemberStatus({ member }: { member: Member }) {
  if (!member.is_active)
    return <span className="flex items-center gap-1 text-xs text-red-400"><ShieldOff size={12} /> Bloqueado</span>;
  if (member.invite_expired)
    return <span className="flex items-center gap-1 text-xs text-orange-400"><AlertTriangle size={12} /> Convite expirado</span>;
  if (member.invite_pending)
    return <span className="flex items-center gap-1 text-xs text-yellow-400"><Clock size={12} /> Convite pendente</span>;
  return <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 size={12} /> Ativo</span>;
}

export function ProjectTeamPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user: currentUser } = useAuthStore();
  const queryClient = useQueryClient();
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteName, setInviteName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("developer");
  const [confirmRemove, setConfirmRemove] = useState<Member | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => api.get(`/projects/${projectId}/members`).then((r) => r.data),
  });

  const members: Member[] = data?.data ?? [];
  const canManage = ["admin", "project_manager"].includes(currentUser?.role ?? "");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["project-members", projectId] });

  const handleInvite = async () => {
    if (!inviteName.trim() || !inviteEmail.trim()) return;
    setActionLoading("invite");
    try {
      const res = await api.post(`/projects/${projectId}/members/invite`, {
        name: inviteName.trim(),
        email: inviteEmail.trim(),
        role: inviteRole,
      });
      toast.success(res.data.message ?? "Convite enviado!");
      setInviteName(""); setInviteEmail(""); setInviteRole("developer");
      setShowInvite(false);
      refresh();
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Falha ao enviar convite.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRoleChange = async (member: Member, role: string) => {
    setActionLoading(member.user_id + "_role");
    try {
      await api.patch(`/projects/${projectId}/members/${member.user_id}`, { role });
      toast.success("Perfil atualizado.");
      refresh();
    } catch {
      toast.error("Não foi possível atualizar o perfil.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleActive = async (member: Member) => {
    setActionLoading(member.user_id + "_active");
    try {
      await api.patch(`/projects/${projectId}/members/${member.user_id}`, { is_active: !member.is_active });
      toast.success(member.is_active ? "Membro bloqueado." : "Membro reativado.");
      refresh();
    } catch {
      toast.error("Não foi possível alterar o status.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResend = async (member: Member) => {
    setActionLoading(member.user_id + "_resend");
    try {
      const res = await api.post(`/projects/${projectId}/members/${member.user_id}/resend-invite`);
      toast.success(res.data.message ?? "Convite reenviado.");
      refresh();
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Falha ao reenviar.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemove = async (member: Member) => {
    setActionLoading(member.user_id + "_remove");
    try {
      await api.delete(`/projects/${projectId}/members/${member.user_id}`);
      toast.success(`${member.name} removido do projeto.`);
      setConfirmRemove(null);
      refresh();
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Não foi possível remover.");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users size={22} className="text-violet-400" />
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            Equipe do Projeto
            <HelpIcon text="Gerencie os membros do projeto e seus perfis de acesso (RBAC). Cada perfil define o que o membro pode ver e fazer: Admin gerencia tudo, Tech Lead aprova overrides e descarta gaps, QA Engineer gerencia planos de teste, Desenvolvedor acessa código gerado, Stakeholder visualiza dashboards." />
          </h1>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="flex items-center gap-2 text-sm text-gray-400 hover:text-white transition-colors">
            <RefreshCw size={14} /> Atualizar
          </button>
          {canManage && (
            <button onClick={() => setShowInvite(true)} className="btn-primary flex items-center gap-2 text-sm">
              <UserPlus size={14} /> Convidar
            </button>
          )}
        </div>
      </div>

      {/* Modal de convite */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card max-w-md w-full mx-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <Mail size={16} className="text-violet-400" /> Convidar para o projeto
              </h3>
              <button onClick={() => setShowInvite(false)} className="text-gray-500 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Nome completo</label>
                <input type="text" value={inviteName} onChange={(e) => setInviteName(e.target.value)}
                  className="input-field" placeholder="Ex: João Silva" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">E-mail</label>
                <input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                  className="input-field" placeholder="joao@empresa.com" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Perfil no projeto</label>
                <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} className="input-field">
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
            </div>
            <p className="text-xs text-gray-500">
              Um e-mail com credenciais temporárias será enviado. O convite expira em <strong className="text-gray-400">72 horas</strong>.
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowInvite(false)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
                Cancelar
              </button>
              <button onClick={handleInvite} disabled={!inviteName.trim() || !inviteEmail.trim() || actionLoading === "invite"}
                className="btn-primary text-sm disabled:opacity-50">
                {actionLoading === "invite" ? "Enviando..." : "Enviar convite"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tabela de membros */}
      {isLoading ? (
        <div className="text-gray-500 text-sm">Carregando equipe...</div>
      ) : isError ? (
        <div className="card border-red-700/50 bg-red-950/10 text-red-300 text-sm">Não foi possível carregar a equipe.</div>
      ) : members.length === 0 ? (
        <div className="card text-center text-gray-500 text-sm py-12">
          Nenhum membro ainda. {canManage && "Use o botão Convidar para adicionar pessoas."}
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-800">
              <tr className="text-gray-500 text-xs uppercase">
                <th className="text-left px-4 py-3">Membro</th>
                <th className="text-left px-4 py-3">Perfil</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Último acesso</th>
                {canManage && <th className="text-right px-4 py-3">Ações</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {members.map((member) => (
                <tr key={member.user_id} className="hover:bg-dark-100 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{member.name}</div>
                    <div className="text-xs text-gray-500">{member.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    {canManage ? (
                      <select
                        value={member.role}
                        onChange={(e) => handleRoleChange(member, e.target.value)}
                        disabled={!!actionLoading}
                        className="input-field text-xs py-1 px-2 w-auto"
                      >
                        {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                      </select>
                    ) : (
                      <span className="text-gray-300">{ROLES.find((r) => r.value === member.role)?.label ?? member.role}</span>
                    )}
                  </td>
                  <td className="px-4 py-3"><MemberStatus member={member} /></td>
                  <td className="px-4 py-3 text-gray-500 text-xs">
                    {member.last_login_at ? new Date(member.last_login_at).toLocaleDateString("pt-BR") : "Nunca"}
                  </td>
                  {canManage && (
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {(member.invite_pending || member.invite_expired) && (
                          <button
                            onClick={() => handleResend(member)}
                            disabled={!!actionLoading}
                            title="Reenviar convite"
                            className="p-1.5 rounded text-gray-500 hover:text-violet-400 hover:bg-violet-900/20 transition-colors disabled:opacity-40"
                          >
                            <Mail size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => handleToggleActive(member)}
                          disabled={!!actionLoading || member.user_id === currentUser?.id}
                          title={member.is_active ? "Bloquear acesso" : "Reativar acesso"}
                          className="p-1.5 rounded text-gray-500 hover:text-yellow-400 hover:bg-yellow-900/20 transition-colors disabled:opacity-40"
                        >
                          {member.is_active ? <ShieldOff size={14} /> : <ShieldCheck size={14} />}
                        </button>
                        <button
                          onClick={() => setConfirmRemove(member)}
                          disabled={!!actionLoading || member.user_id === currentUser?.id}
                          title="Remover do projeto"
                          className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-40"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal confirmação de remoção */}
      {confirmRemove && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="card max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-red-900/30"><Trash2 size={18} className="text-red-400" /></div>
              <div>
                <h3 className="font-semibold text-white">Remover membro</h3>
                <p className="text-xs text-gray-400">Esta ação remove o acesso ao projeto.</p>
              </div>
            </div>
            <p className="text-sm text-gray-300">
              Remover <span className="text-white font-semibold">{confirmRemove.name}</span> ({confirmRemove.email}) do projeto?
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setConfirmRemove(null)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancelar</button>
              <button
                onClick={() => handleRemove(confirmRemove)}
                disabled={actionLoading === confirmRemove.user_id + "_remove"}
                className="px-4 py-2 rounded-lg text-sm bg-red-600 hover:bg-red-700 text-white font-medium disabled:opacity-50"
              >
                {actionLoading === confirmRemove.user_id + "_remove" ? "Removendo..." : "Remover"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
