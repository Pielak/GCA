/**
 * Módulo 15 — Backup & Recovery
 * GPD v4.0 — Apenas Admin
 */
import { useState } from "react";
import { HelpIcon } from "@/components/HelpIcon";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  DatabaseBackup, RefreshCw, Download, AlertTriangle,
  CheckCircle, XCircle, Clock, Server, Shield, RotateCcw, Calendar,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

interface BackupStatus {
  total_backups: number;
  last_backup_at: string | null;
  last_backup_size: string | null;
  last_backup_file: string | null;
  backup_dir: string;
  backup_server_configured: boolean;
  next_scheduled_backup: string | null;
}

interface BackupFile {
  filename: string;
  size_bytes: number;
  size_human: string;
  created_at: string;
}

export function BackupRecoveryPage() {
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";

  const [recoveryFile, setRecoveryFile] = useState("");
  const [recoveryConfirm, setRecoveryConfirm] = useState(false);
  const [label, setLabel] = useState("");

  const { data: statusData, isLoading: statusLoading, refetch: refetchStatus } = useQuery<{ success: boolean; data: BackupStatus }>({
    queryKey: ["backup-status"],
    queryFn: () => api.get("/admin/backup/status").then(r => r.data),
    enabled: isAdmin,
    refetchInterval: 30000,
  });

  const { data: listData, isLoading: listLoading, refetch: refetchList } = useQuery<{ success: boolean; data: BackupFile[] }>({
    queryKey: ["backup-list"],
    queryFn: () => api.get("/admin/backup/list").then(r => r.data),
    enabled: isAdmin,
  });

  const createBackupMutation = useMutation({
    mutationFn: (label: string) => api.post("/admin/backup", { label }),
    onSuccess: () => {
      toast.success("Backup iniciado. Aguarde alguns segundos e atualize a lista.");
      setTimeout(() => {
        refetchList();
        refetchStatus();
      }, 6000);
    },
    onError: () => toast.error("Não foi possível iniciar o backup. Verifique se o banco está acessível."),
  });

  const syncMutation = useMutation({
    mutationFn: (backup_file: string | null) => api.post("/admin/backup/sync", { backup_file }),
    onSuccess: () => toast.success("Sincronização com servidor de backup iniciada."),
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || "Não foi possível sincronizar. Verifique DATABASE_BACKUP_URL no .env."),
  });

  const recoveryMutation = useMutation({
    mutationFn: ({ backup_file, confirm }: { backup_file: string; confirm: boolean }) =>
      api.post("/admin/backup/recovery", { backup_file, confirm }),
    onSuccess: () => {
      toast.success("Recovery concluído. Redirecionando para login...");
      setTimeout(() => { window.location.href = "/login"; }, 3000);
    },
    onError: (e: any) =>
      toast.error(e.response?.data?.detail || "Recovery falhou. O banco pode estar inconsistente — contate o DBA."),
  });

  if (!isAdmin) {
    return (
      <div className="card text-center py-16">
        <Shield size={40} className="mx-auto mb-3 text-red-600" />
        <p className="text-red-400 font-semibold">Acesso restrito</p>
        <p className="text-gray-500 text-sm mt-1">
          O módulo de Backup & Recovery é exclusivo para o perfil Admin.
        </p>
      </div>
    );
  }

  const status = statusData?.data;
  const backups = listData?.data ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <h1 className="text-2xl font-bold text-white flex items-center gap-2">
        <DatabaseBackup size={22} className="text-violet-400" />
        Backup & Recovery
        <HelpIcon text="Backups automáticos são criados a cada hora e os 5 mais recentes são mantidos. Em caso de incidente (queda de energia, falha de hardware, corrupção de dados), selecione um ponto de restauração e execute o Recovery. Toda ação é registrada na trilha de auditoria." />
      </h1>

      {/* Status cards */}
      {statusLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-pulse h-20" />
          ))}
        </div>
      ) : status && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Total de backups</p>
            <p className="text-2xl font-bold text-white">{status.total_backups}<span className="text-sm text-gray-500 font-normal ml-1">/ 5 max</span></p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Último backup</p>
            <p className="text-sm font-semibold text-white">
              {status.last_backup_at
                ? new Date(status.last_backup_at).toLocaleString("pt-BR")
                : <span className="text-amber-400">Nenhum ainda</span>}
            </p>
            {status.last_backup_size && (
              <p className="text-xs text-gray-500">{status.last_backup_size}</p>
            )}
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 mb-1 flex items-center gap-1">
              <Calendar size={11} />
              Próximo backup automático
            </p>
            <p className="text-sm font-semibold text-violet-300">
              {status.next_scheduled_backup
                ? new Date(status.next_scheduled_backup).toLocaleString("pt-BR")
                : "—"}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">Frequência: a cada hora</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Servidor de backup</p>
            <div className="flex items-center gap-2">
              {status.backup_server_configured ? (
                <><CheckCircle size={16} className="text-emerald-400" />
                <span className="text-sm text-emerald-300">Configurado</span></>
              ) : (
                <><XCircle size={16} className="text-amber-400" />
                <span className="text-sm text-amber-300">Não configurado</span></>
              )}
            </div>
            {!status.backup_server_configured && (
              <p className="text-xs text-gray-600 mt-1">
                Configure DATABASE_BACKUP_URL no .env
              </p>
            )}
          </div>
        </div>
      )}

      {/* Criar backup manual */}
      <div className="card">
        <h2 className="font-semibold text-white mb-3 flex items-center gap-2">
          <Download size={16} className="text-violet-400" />
          Criar Backup Manual
        </h2>
        <div className="flex gap-3 flex-wrap">
          <input
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="Rótulo (opcional): ex: pre-deploy-v2"
            className="input-field flex-1 min-w-48"
          />
          <button
            onClick={() => { createBackupMutation.mutate(label); setLabel(""); }}
            disabled={createBackupMutation.isPending}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            <Download size={14} />
            {createBackupMutation.isPending ? "Iniciando..." : "Criar Backup"}
          </button>
          {status?.backup_server_configured && (
            <button
              onClick={() => syncMutation.mutate(null)}
              disabled={syncMutation.isPending}
              className="btn-secondary flex items-center gap-2 disabled:opacity-50"
            >
              <Server size={14} />
              {syncMutation.isPending ? "Sincronizando..." : "Sync → Backup"}
            </button>
          )}
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Backups automáticos já ocorrem a cada hora. Use o manual antes de deploys ou mudanças críticas.
          Mantidos os 5 mais recentes; os anteriores são removidos automaticamente.
        </p>
      </div>

      {/* Lista de backups + Recovery integrado */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <Clock size={16} className="text-violet-400" />
            Pontos de Restauração
          </h2>
          <button
            onClick={() => { refetchList(); refetchStatus(); }}
            className="text-gray-500 hover:text-gray-200 transition-colors"
            title="Atualizar lista"
          >
            <RefreshCw size={14} />
          </button>
        </div>

        {listLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-14 animate-pulse bg-dark-200 rounded-lg" />
            ))}
          </div>
        ) : backups.length === 0 ? (
          <div className="text-center py-8 space-y-2">
            <DatabaseBackup size={32} className="text-gray-600 mx-auto" />
            <p className="text-gray-400 font-medium">Nenhum backup disponível ainda</p>
            <p className="text-gray-500 text-sm">
              O primeiro backup automático ocorrerá na próxima hora.<br />
              Você pode criar um manual agora usando o botão acima.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {backups.map(b => (
              <div
                key={b.filename}
                className={clsx(
                  "flex items-center justify-between p-3 rounded-lg border transition-colors",
                  recoveryFile === b.filename
                    ? "bg-amber-900/10 border-amber-700/50"
                    : "bg-dark-200 border-transparent hover:border-gray-700"
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-mono text-gray-200 truncate">{b.filename}</p>
                  <p className="text-xs text-gray-500">
                    {new Date(b.created_at).toLocaleString("pt-BR")} · {b.size_human}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0 ml-3">
                  {status?.backup_server_configured && (
                    <button
                      onClick={() => syncMutation.mutate(b.filename)}
                      disabled={syncMutation.isPending}
                      className="text-xs px-2 py-1 rounded border border-gray-700 text-gray-400 hover:text-violet-300 hover:border-violet-700 transition-colors disabled:opacity-40"
                    >
                      Sync
                    </button>
                  )}
                  <button
                    onClick={() => {
                      setRecoveryFile(recoveryFile === b.filename ? "" : b.filename);
                      setRecoveryConfirm(false);
                    }}
                    className={clsx(
                      "text-xs px-3 py-1 rounded border transition-colors flex items-center gap-1.5",
                      recoveryFile === b.filename
                        ? "bg-amber-900/30 text-amber-300 border-amber-700"
                        : "text-gray-400 border-gray-700 hover:border-amber-700 hover:text-amber-300"
                    )}
                  >
                    <RotateCcw size={11} />
                    {recoveryFile === b.filename ? "Selecionado" : "Restaurar"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Painel de Recovery — sempre presente se nenhum backup selecionado mostra instrução */}
      <div className={clsx(
        "card border transition-colors",
        recoveryFile ? "border-red-700/50 bg-red-900/10" : "border-gray-700/50"
      )}>
        <h2 className={clsx(
          "font-bold flex items-center gap-2 mb-3",
          recoveryFile ? "text-red-400" : "text-gray-400"
        )}>
          <AlertTriangle size={18} />
          Recovery — Restauração de Ponto de Backup
        </h2>

        {!recoveryFile ? (
          <div className="text-center py-6 space-y-2">
            <RotateCcw size={28} className="text-gray-600 mx-auto" />
            <p className="text-gray-500 text-sm">
              Selecione um ponto de restauração na lista acima clicando em <strong className="text-gray-400">Restaurar</strong>.
            </p>
            <p className="text-gray-600 text-xs max-w-lg mx-auto">
              Use em caso de incidente: queda de energia, falha de hardware, corrupção de dados ou atualização com falha.
              O banco será restaurado exatamente ao estado do backup selecionado.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="bg-red-900/20 border border-red-700/40 rounded-lg p-3 space-y-1.5">
              <p className="text-red-300 font-semibold text-sm">Ponto de restauração selecionado:</p>
              <p className="font-mono text-amber-300 text-sm bg-dark-200 px-3 py-1.5 rounded">{recoveryFile}</p>
            </div>

            <div className="bg-red-900/20 border border-red-700/40 rounded-lg p-3 space-y-1">
              <p className="text-red-300 font-semibold text-sm">Consequências desta operação:</p>
              <p className="text-red-400 text-sm">• Todos os dados atuais serão substituídos pelos dados deste backup</p>
              <p className="text-red-400 text-sm">• Dados criados após o backup serão perdidos permanentemente</p>
              <p className="text-red-400 text-sm">• Todas as sessões ativas serão encerradas (novo login necessário)</p>
              <p className="text-red-400 text-sm">• Esta ação é registrada permanentemente na trilha de auditoria</p>
            </div>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={recoveryConfirm}
                onChange={e => setRecoveryConfirm(e.target.checked)}
                className="w-4 h-4 mt-0.5 accent-red-600 shrink-0"
              />
              <span className="text-gray-300 text-sm">
                Entendo que esta operação é <strong className="text-red-300">irreversível</strong> e confirmo a restauração do banco ao estado do backup selecionado.
              </span>
            </label>

            <div className="flex gap-3">
              <button
                onClick={() => recoveryMutation.mutate({ backup_file: recoveryFile, confirm: recoveryConfirm })}
                disabled={!recoveryConfirm || recoveryMutation.isPending}
                className="flex items-center gap-2 px-5 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white text-sm font-semibold rounded-lg transition-colors"
              >
                <RotateCcw size={14} />
                {recoveryMutation.isPending ? "Restaurando..." : "Executar Recovery"}
              </button>
              <button
                onClick={() => { setRecoveryFile(""); setRecoveryConfirm(false); }}
                className="btn-secondary"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
