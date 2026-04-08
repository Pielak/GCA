/**
 * Módulo 13 — Integrações de Comunicação
 * GPD v4.0 — Slack, Microsoft Teams, E-mail transacional
 */
import { useState } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, Controller } from "react-hook-form";
import toast from "react-hot-toast";
import {
  Bell, Plus, Trash2, Send, ToggleLeft, ToggleRight,
  CheckCircle, XCircle, Clock,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

// ─── Types ───────────────────────────────────────────────────

type Channel = "slack" | "teams" | "email";

interface NotificationConfig {
  id: string;
  channel: Channel;
  label: string;
  has_webhook: boolean;
  email_recipients: string[];
  events: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  last_delivery_status: "ok" | "failed" | null;
  last_delivery_error: string | null;
  created_at: string;
  updated_at: string;
}

// ─── Constants ────────────────────────────────────────────────

const CHANNEL_CONFIG: Record<Channel, { label: string; color: string; placeholder: string }> = {
  slack: {
    label: "Slack",
    color: "bg-green-900/40 text-green-300 border-green-700/50",
    placeholder: "https://hooks.slack.com/services/...",
  },
  teams: {
    label: "Microsoft Teams",
    color: "bg-blue-900/40 text-blue-300 border-blue-700/50",
    placeholder: "https://outlook.office.com/webhook/...",
  },
  email: {
    label: "E-mail",
    color: "bg-amber-900/40 text-amber-300 border-amber-700/50",
    placeholder: "",
  },
};

const EVENT_LABELS: Record<string, string> = {
  gatekeeper_approved: "Gatekeeper aprovado",
  gatekeeper_blocked: "Gatekeeper bloqueado",
  show_stopper_created: "Show Stopper criado no QA",
  codegen_completed: "Geração de código concluída",
  codegen_failed: "Geração de código falhou",
  artifact_quarantine: "Artefato em quarentena LGPD",
  legacy_analysis_done: "Análise de legado concluída",
  legacy_access_expiring: "Acesso ao legado expirando (7 dias)",
  repo_token_expiring: "Token de repositório expirando (7 dias)",
  user_created: "Novo usuário criado",
  password_reset: "Senha redefinida por admin",
  project_created: "Novo projeto criado",
};

const WRITE_ROLES = new Set(["admin", "project_manager", "tech_lead"]);

// ─── Component ────────────────────────────────────────────────

export function NotificationsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const canWrite = user ? WRITE_ROLES.has(user.role) : false;

  const [showForm, setShowForm] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);

  const { data: eventsData } = useQuery<{ success: boolean; data: string[] }>({
    queryKey: ["notification-events"],
    queryFn: () => api.get(`/projects/${projectId}/notifications/events`).then(r => r.data),
  });

  const { data, isLoading } = useQuery<{ success: boolean; data: NotificationConfig[] }>({
    queryKey: ["notifications", projectId],
    queryFn: () => api.get(`/projects/${projectId}/notifications`).then(r => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (body: object) => api.post(`/projects/${projectId}/notifications`, body),
    onSuccess: () => {
      toast.success("Canal de notificação criado!");
      qc.invalidateQueries({ queryKey: ["notifications", projectId] });
      setShowForm(false);
      reset();
    },
    onError: (e: any) =>
      toast.error(
        e.response?.data?.detail ||
        "Não foi possível criar o canal. Verifique a URL do webhook e os eventos selecionados."
      ),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/projects/${projectId}/notifications/${id}`),
    onSuccess: () => {
      toast.success("Canal removido.");
      qc.invalidateQueries({ queryKey: ["notifications", projectId] });
    },
    onError: () => toast.error("Não foi possível remover o canal. Tente novamente."),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch(`/projects/${projectId}/notifications/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", projectId] }),
    onError: () => toast.error("Não foi possível alterar o estado do canal."),
  });

  const { register, handleSubmit, reset, watch, control } = useForm<{
    channel: Channel;
    label: string;
    webhook_url: string;
    email_recipients_raw: string;
    events: string[];
  }>({ defaultValues: { channel: "slack", events: [] } });

  const watchChannel = watch("channel");
  const allEvents = eventsData?.data ?? Object.keys(EVENT_LABELS);
  const configs = data?.data ?? [];

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      await api.post(`/projects/${projectId}/notifications/${id}/test`, {
        event: "gatekeeper_approved",
      });
      toast.success("Notificação de teste enviada com sucesso!");
    } catch (e: any) {
      toast.error(
        e.response?.data?.detail ||
        "Não foi possível enviar a notificação de teste. Verifique a URL do webhook ou as configurações de SMTP."
      );
    } finally {
      setTestingId(null);
    }
  };

  const onSubmit = (d: any) => {
    const recipients =
      d.email_recipients_raw
        ? d.email_recipients_raw.split(/[,;\n]/).map((e: string) => e.trim()).filter(Boolean)
        : [];
    createMutation.mutate({
      channel: d.channel,
      label: d.label,
      webhook_url: d.webhook_url || undefined,
      email_recipients: recipients,
      events: d.events,
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Bell size={22} className="text-violet-400" />
          Notificações
          <HelpIcon text="Configure canais de notificação (Slack, Teams, e-mail) para eventos críticos do projeto: aprovações do Gatekeeper, Show Stoppers, conclusão de geração de código e muito mais." />
        </h1>
        {canWrite && (
          <button onClick={() => setShowForm(!showForm)} className="btn-primary flex items-center gap-2">
            <Plus size={16} />
            Novo Canal
          </button>
        )}
      </div>

      {/* Form */}
      {showForm && canWrite && (
        <div className="card border-violet-700/50">
          <h3 className="font-semibold text-white mb-4">Configurar Canal de Notificação</h3>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">Canal</label>
                <select {...register("channel")} className="input-field">
                  <option value="slack">Slack</option>
                  <option value="teams">Microsoft Teams</option>
                  <option value="email">E-mail</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">Nome descritivo</label>
                <input
                  {...register("label", { required: true })}
                  className="input-field"
                  placeholder="Canal #gpd-alertas"
                />
              </div>
            </div>

            {watchChannel !== "email" && (
              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  Webhook URL ({CHANNEL_CONFIG[watchChannel]?.label})
                </label>
                <input
                  {...register("webhook_url")}
                  className="input-field"
                  placeholder={CHANNEL_CONFIG[watchChannel]?.placeholder}
                />
              </div>
            )}

            {watchChannel === "email" && (
              <div>
                <label className="block text-sm text-gray-300 mb-1">
                  Destinatários (separados por vírgula ou quebra de linha)
                </label>
                <textarea
                  {...register("email_recipients_raw")}
                  className="input-field min-h-[80px] resize-none"
                  placeholder="dev@empresa.com, pm@empresa.com"
                />
              </div>
            )}

            <div>
              <label className="block text-sm text-gray-300 mb-2">
                Eventos que disparam notificação
              </label>
              <div className="grid grid-cols-2 gap-2">
                {allEvents.map(evt => (
                  <label key={evt} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      value={evt}
                      {...register("events")}
                      className="w-4 h-4 accent-violet-600"
                    />
                    <span className="text-sm text-gray-300">
                      {EVENT_LABELS[evt] ?? evt}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="btn-primary disabled:opacity-50"
              >
                {createMutation.isPending ? "Salvando..." : "Salvar Canal"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Channel list */}
      {isLoading ? (
        <div className="text-gray-500 text-sm animate-pulse py-8 text-center">Carregando canais...</div>
      ) : configs.length === 0 ? (
        <div className="card text-center py-16 text-gray-500">
          <Bell size={36} className="mx-auto mb-3 text-gray-700" />
          <p>Nenhum canal configurado.</p>
          {canWrite && (
            <p className="text-sm mt-1">
              Clique em{" "}
              <button className="text-violet-400 hover:underline" onClick={() => setShowForm(true)}>
                Novo Canal
              </button>{" "}
              para começar.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {configs.map(cfg => {
            const chCfg = CHANNEL_CONFIG[cfg.channel];
            return (
              <div
                key={cfg.id}
                className={clsx("card", !cfg.is_active && "opacity-60")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={clsx("text-xs px-2 py-0.5 rounded-full border", chCfg.color)}
                      >
                        {chCfg.label}
                      </span>
                      <span className="font-semibold text-white">{cfg.label}</span>
                      {!cfg.is_active && (
                        <span className="text-xs text-gray-500 italic">desativado</span>
                      )}
                    </div>

                    {/* Events */}
                    <div className="flex flex-wrap gap-1 mt-2">
                      {cfg.events.map(evt => (
                        <span
                          key={evt}
                          className="text-xs px-2 py-0.5 rounded-full bg-dark-200 text-gray-400 border border-gray-700/50"
                        >
                          {EVENT_LABELS[evt] ?? evt}
                        </span>
                      ))}
                    </div>

                    {cfg.channel === "email" && cfg.email_recipients.length > 0 && (
                      <p className="text-xs text-gray-500 mt-1">
                        Destinatários: {cfg.email_recipients.join(", ")}
                      </p>
                    )}

                    {/* Last delivery */}
                    {cfg.last_delivery_at && (
                      <div className="flex items-center gap-1.5 mt-2 text-xs">
                        {cfg.last_delivery_status === "ok" ? (
                          <CheckCircle size={12} className="text-emerald-400" />
                        ) : (
                          <XCircle size={12} className="text-red-400" />
                        )}
                        <span className="text-gray-500">
                          Última entrega: {new Date(cfg.last_delivery_at).toLocaleString("pt-BR")}
                          {cfg.last_delivery_error && (
                            <span className="text-red-400 ml-1">— {cfg.last_delivery_error}</span>
                          )}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {canWrite && (
                      <>
                        <button
                          onClick={() => handleTest(cfg.id)}
                          disabled={testingId === cfg.id}
                          title="Enviar teste"
                          className="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 border border-violet-700/50 px-2 py-1 rounded-lg disabled:opacity-40"
                        >
                          <Send size={12} />
                          {testingId === cfg.id ? "Enviando..." : "Testar"}
                        </button>

                        <button
                          onClick={() => toggleMutation.mutate({ id: cfg.id, is_active: !cfg.is_active })}
                          title={cfg.is_active ? "Desativar" : "Ativar"}
                          className="text-gray-500 hover:text-violet-400"
                        >
                          {cfg.is_active ? (
                            <ToggleRight size={20} className="text-emerald-400" />
                          ) : (
                            <ToggleLeft size={20} />
                          )}
                        </button>

                        <button
                          onClick={() => {
                            if (confirm(`Remover canal "${cfg.label}"?`)) {
                              deleteMutation.mutate(cfg.id);
                            }
                          }}
                          title="Remover"
                          className="text-gray-500 hover:text-red-400"
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
