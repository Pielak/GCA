import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users, Plus, Search, Shield, ShieldOff, KeyRound,
  RefreshCw, CheckCircle2, XCircle, Crown, Edit3, X, Check,
} from "lucide-react";
import { toast } from "react-hot-toast";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────────────────────

interface UserRow {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

interface RoleOption {
  value: string;
  label: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin:           "Admin",
  project_manager: "Gerente de Projeto",
  tech_lead:       "Tech Lead",
  dev_senior:      "Dev Sênior",
  dev_pleno:       "Dev Pleno",
  qa_engineer:     "QA Engineer",
  compliance:      "Compliance",
  security:        "Segurança",
  scrum_master:    "Scrum Master",
  legal:           "Jurídico",
  stakeholder:     "Stakeholder",
};

function roleBadge(role: string) {
  if (role === "admin") return "bg-violet-900/60 text-violet-200 border border-violet-600/60";
  if (role === "tech_lead") return "bg-blue-900/50 text-blue-300 border border-blue-700/50";
  if (role === "project_manager") return "bg-cyan-900/50 text-cyan-300 border border-cyan-700/50";
  if (role === "dev_senior" || role === "dev_pleno") return "bg-emerald-900/50 text-emerald-300 border border-emerald-700/50";
  return "bg-gray-800/50 text-gray-400 border border-gray-700/50";
}

// ─── Create Modal ─────────────────────────────────────────────────────────────

function CreateUserModal({ roles, onClose }: { roles: RoleOption[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("developer");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/users", {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        role,
        password: password.trim() || undefined,
      });
      return data;
    },
    onSuccess: (data) => {
      toast.success(`Usuário criado.${data.temp_password ? ` Senha temporária: ${data.temp_password}` : ""}`);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      onClose();
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao criar usuário.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-dark-100 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4 mx-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white flex items-center gap-2">
            <Plus size={16} className="text-violet-400" /> Novo Usuário
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 font-medium">Nome completo *</label>
            <input className="input-field text-sm mt-1" value={name} onChange={e => setName(e.target.value)} placeholder="Ex: João Silva" />
          </div>
          <div>
            <label className="text-xs text-gray-400 font-medium">E-mail *</label>
            <input className="input-field text-sm mt-1" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="joao@empresa.com" />
          </div>
          <div>
            <label className="text-xs text-gray-400 font-medium">Perfil *</label>
            <select className="input-field text-sm mt-1" value={role} onChange={e => setRole(e.target.value)}>
              {roles.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            {role === "admin" && (
              <p className="text-xs text-violet-400 mt-1 flex items-center gap-1">
                <Crown size={10} /> Este usuário terá acesso total ao sistema.
              </p>
            )}
          </div>
          <div>
            <label className="text-xs text-gray-400 font-medium">
              Senha <span className="text-gray-600">(deixe em branco para gerar automaticamente)</span>
            </label>
            <input className="input-field text-sm mt-1" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Mínimo 8 caracteres" />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary text-sm" onClick={onClose} disabled={mutation.isPending}>Cancelar</button>
          <button
            className="btn-primary text-sm flex items-center gap-2"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim() || !email.trim()}
          >
            {mutation.isPending
              ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <Check size={14} />}
            Criar Usuário
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Edit Row Modal ───────────────────────────────────────────────────────────

function EditUserModal({
  user, roles, onClose,
}: { user: UserRow; roles: RoleOption[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const me = useAuthStore(s => s.user);
  const [role, setRole] = useState(user.role);
  const [isActive, setIsActive] = useState(user.is_active);

  const mutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.patch(`/users/${user.id}`, {
        role: role !== user.role ? role : undefined,
        is_active: isActive !== user.is_active ? isActive : undefined,
      });
      return data;
    },
    onSuccess: () => {
      toast.success("Usuário atualizado.");
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      onClose();
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao atualizar usuário.");
    },
  });

  const isSelf = me?.id === user.id;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-dark-100 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4 mx-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white flex items-center gap-2">
            <Edit3 size={16} className="text-violet-400" /> Editar Usuário
          </h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300"><X size={16} /></button>
        </div>

        <div className="bg-dark-200 rounded-lg px-3 py-2 space-y-0.5">
          <p className="text-sm text-gray-200 font-medium">{user.name}</p>
          <p className="text-xs text-gray-500">{user.email}</p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 font-medium">Perfil</label>
            <select className="input-field text-sm mt-1" value={role} onChange={e => setRole(e.target.value)} disabled={isSelf}>
              {roles.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            {role === "admin" && role !== user.role && (
              <p className="text-xs text-violet-400 mt-1 flex items-center gap-1">
                <Crown size={10} /> Este usuário passará a ter acesso total ao sistema.
              </p>
            )}
            {isSelf && (
              <p className="text-xs text-amber-500 mt-1">Você não pode alterar seu próprio perfil.</p>
            )}
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-gray-400 font-medium">Status</p>
              <p className="text-xs text-gray-600 mt-0.5">
                {isActive ? "Usuário ativo — pode fazer login" : "Usuário inativo — acesso bloqueado"}
              </p>
            </div>
            <button
              onClick={() => setIsActive(v => !v)}
              disabled={isSelf}
              className={clsx(
                "w-10 h-5 rounded-full transition-colors relative",
                isActive ? "bg-emerald-600" : "bg-gray-700",
                isSelf && "opacity-40 cursor-not-allowed"
              )}
            >
              <span className={clsx(
                "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                isActive ? "translate-x-5" : "translate-x-0.5"
              )} />
            </button>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-secondary text-sm" onClick={onClose} disabled={mutation.isPending}>Cancelar</button>
          <button
            className="btn-primary text-sm flex items-center gap-2"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || (role === user.role && isActive === user.is_active)}
          >
            {mutation.isPending
              ? <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              : <Check size={14} />}
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const me = useAuthStore(s => s.user);
  const [search, setSearch] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterActive, setFilterActive] = useState<"" | "true" | "false">("");
  const [showCreate, setShowCreate] = useState(false);
  const [editUser, setEditUser] = useState<UserRow | null>(null);

  const { data: users = [], isLoading } = useQuery<UserRow[]>({
    queryKey: ["admin-users", search, filterRole, filterActive],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      if (filterRole) params.role = filterRole;
      if (filterActive !== "") params.is_active = filterActive;
      const { data } = await api.get<{ success: boolean; data: UserRow[] }>("/users", { params });
      return data.data;
    },
  });

  const { data: rolesData = [] } = useQuery<string[]>({
    queryKey: ["roles"],
    queryFn: async () => {
      const { data } = await api.get<{ success: boolean; data: string[] }>("/users/roles");
      return data.data;
    },
  });

  const roles: RoleOption[] = rolesData.map(r => ({ value: r, label: ROLE_LABELS[r] ?? r }));

  const resetPasswordMutation = useMutation({
    mutationFn: async (userId: string) => {
      const { data } = await api.post(`/users/${userId}/reset-password`);
      return data;
    },
    onSuccess: (data) => {
      toast.success(
        data.temp_password
          ? `Senha resetada. Temporária: ${data.temp_password}`
          : "Senha resetada e enviada por e-mail."
      );
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.message ?? "Erro ao resetar senha.");
    },
  });

  const admins = users.filter(u => u.role === "admin" && u.is_active);

  return (
    <div className="flex flex-col gap-6 h-full">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Users size={24} className="text-violet-400" />
          Gestão de Usuários
        </h1>
        <button className="btn-primary flex items-center gap-2" onClick={() => setShowCreate(true)}>
          <Plus size={16} /> Novo Usuário
        </button>
      </div>

      {/* Admin count banner */}
      <div className={clsx(
        "flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm shrink-0",
        admins.length === 1
          ? "bg-amber-900/20 border-amber-700/40 text-amber-300"
          : "bg-violet-900/20 border-violet-700/40 text-violet-300"
      )}>
        <Crown size={14} className={admins.length === 1 ? "text-amber-400" : "text-violet-400"} />
        <span>
          {admins.length === 1
            ? `Atenção: apenas 1 admin ativo (${admins[0]?.name}). Recomendado ter ao menos 2 para cobertura em caso de ausência.`
            : `${admins.length} admins ativos: ${admins.map(a => a.name).join(", ")}.`}
        </span>
      </div>

      {/* Filters */}
      <div className="flex gap-3 shrink-0 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            className="input-field text-sm pl-8"
            placeholder="Buscar por nome ou e-mail..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <select className="input-field text-sm w-48" value={filterRole} onChange={e => setFilterRole(e.target.value)}>
          <option value="">Todos os perfis</option>
          {roles.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <select className="input-field text-sm w-36" value={filterActive} onChange={e => setFilterActive(e.target.value as any)}>
          <option value="">Qualquer status</option>
          <option value="true">Ativos</option>
          <option value="false">Inativos</option>
        </select>
        <button
          className="text-gray-500 hover:text-gray-300 transition-colors p-2 rounded-lg hover:bg-dark-200"
          onClick={() => queryClient.invalidateQueries({ queryKey: ["admin-users"] })}
          title="Atualizar lista"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0 overflow-auto rounded-xl border border-gray-800">
        {isLoading ? (
          <div className="flex items-center justify-center h-40 text-gray-600">
            <span className="w-5 h-5 border-2 border-gray-700 border-t-gray-400 rounded-full animate-spin mr-2" />
            Carregando...
          </div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-600 gap-2">
            <Users size={28} className="text-gray-700" />
            <p className="text-sm">Nenhum usuário encontrado.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-dark-200 z-10">
              <tr className="border-b border-gray-800">
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Usuário</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Perfil</th>
                <th className="text-center px-4 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Status</th>
                <th className="text-left px-4 py-3 text-xs text-gray-500 font-semibold uppercase tracking-wide">Último login</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {users.map(u => {
                const isSelf = u.id === me?.id;
                return (
                  <tr key={u.id} className={clsx(
                    "hover:bg-dark-200/50 transition-colors",
                    !u.is_active && "opacity-50"
                  )}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={clsx(
                          "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0",
                          u.role === "admin" ? "bg-violet-800/60 text-violet-200" : "bg-dark-300 text-gray-400"
                        )}>
                          {u.name.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-gray-100 font-medium">{u.name}</span>
                            {isSelf && <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/40 text-violet-400 border border-violet-700/40">Você</span>}
                            {u.must_change_password && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-400 border border-amber-700/40">Convite pendente</span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={clsx("text-xs px-2 py-1 rounded-full flex items-center gap-1 w-fit", roleBadge(u.role))}>
                        {u.role === "admin" && <Crown size={9} />}
                        {ROLE_LABELS[u.role] ?? u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {u.is_active
                        ? <CheckCircle2 size={15} className="text-emerald-500 mx-auto" />
                        : <XCircle size={15} className="text-red-500 mx-auto" />}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {u.last_login_at
                        ? new Date(u.last_login_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
                        : "Nunca"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          onClick={() => setEditUser(u)}
                          className="text-gray-600 hover:text-gray-200 transition-colors p-1.5 rounded hover:bg-dark-300"
                          title="Editar perfil / status"
                        >
                          <Edit3 size={13} />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Resetar senha de ${u.name}?`)) {
                              resetPasswordMutation.mutate(u.id);
                            }
                          }}
                          className="text-gray-600 hover:text-amber-400 transition-colors p-1.5 rounded hover:bg-dark-300"
                          title="Resetar senha"
                          disabled={resetPasswordMutation.isPending}
                        >
                          <KeyRound size={13} />
                        </button>
                        {u.is_active
                          ? <Shield size={13} className="text-emerald-700 ml-1" />
                          : <ShieldOff size={13} className="text-red-700 ml-1" />}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Modals */}
      {showCreate && <CreateUserModal roles={roles} onClose={() => setShowCreate(false)} />}
      {editUser && <EditUserModal user={editUser} roles={roles} onClose={() => setEditUser(null)} />}
    </div>
  );
}
