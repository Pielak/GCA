import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Mail } from "lucide-react";
import toast from "react-hot-toast";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

const schema = z
  .object({
    current_password: z.string().min(1, "Digite a senha temporária enviada para o seu e-mail corporativo"),
    new_password: z
      .string()
      .min(8, "A senha deve ter no mínimo 8 caracteres")
      .regex(/[A-Z]/, "Inclua ao menos uma letra maiúscula (A-Z)")
      .regex(/[0-9]/, "Inclua ao menos um número (0-9)")
      .regex(/[^A-Za-z0-9]/, "Inclua ao menos um caractere especial (@, #, !, %, etc.)"),
    confirm_password: z.string().min(1, "Repita a nova senha para confirmar"),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    message: "As senhas não são iguais — verifique e tente novamente",
    path: ["confirm_password"],
  });

type FormData = z.infer<typeof schema>;

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const { isAuthenticated, user, setAuth, access_token, refresh_token } = useAuthStore();
  const [loading, setLoading] = useState(false);

  // Redireciona para login se não estiver autenticado
  useEffect(() => {
    if (!isAuthenticated || !user) {
      navigate("/login", { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    try {
      await api.post("/users/me/change-password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });

      if (user && access_token && refresh_token) {
        setAuth({ ...user, must_change_password: false }, access_token, refresh_token);
      }

      toast.success("Senha definida com sucesso!");
      navigate(user?.role === "admin" ? "/settings/parametrization" : "/dashboard", { replace: true });
    } catch (err: any) {
      toast.error(err.response?.data?.message ?? "Senha temporária incorreta ou expirada. Solicite um novo reset ao administrador se o problema persistir.");
    } finally {
      setLoading(false);
    }
  };

  if (!isAuthenticated || !user) return null;

  return (
    <div className="min-h-screen bg-dark flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-violet-600 flex items-center justify-center mb-3">
            <KeyRound size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Defina sua senha</h1>
          <p className="text-gray-500 text-sm mt-1 text-center">
            Primeiro acesso — crie uma senha pessoal e segura.
          </p>
        </div>

        <div className="card space-y-5">
          {/* Identificação do usuário */}
          <div className="flex items-center gap-2 px-3 py-2 bg-dark rounded-lg border border-gray-700">
            <Mail size={14} className="text-violet-400 shrink-0" />
            <span className="text-sm text-gray-300 truncate">{user.email}</span>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Senha temporária recebida
              </label>
              <input
                {...register("current_password")}
                type="password"
                placeholder="••••••••"
                className="input-field"
                autoComplete="current-password"
                autoFocus
              />
              {errors.current_password && (
                <p className="text-red-400 text-xs mt-1">{errors.current_password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Nova senha</label>
              <input
                {...register("new_password")}
                type="password"
                placeholder="Mín. 8 chars, maiúscula, número, símbolo"
                className="input-field"
                autoComplete="new-password"
              />
              {errors.new_password && (
                <p className="text-red-400 text-xs mt-1">{errors.new_password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Confirmar nova senha</label>
              <input
                {...register("confirm_password")}
                type="password"
                placeholder="••••••••"
                className="input-field"
                autoComplete="new-password"
              />
              {errors.confirm_password && (
                <p className="text-red-400 text-xs mt-1">{errors.confirm_password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {loading && (
                <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              )}
              Definir senha e entrar →
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
