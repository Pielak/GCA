/**
 * Tela de Login — GPD v4.0
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import toast from "react-hot-toast";
import { Eye, EyeOff } from "lucide-react";
import { api } from "@/services/api";
import { useAuthStore } from "@/store/auth";

const schema = z.object({
  email: z.string().email("Informe um e-mail válido (ex: voce@empresa.com)"),
  password: z.string().min(1, "Digite sua senha para continuar"),
});

type FormData = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const { setAuth, clearAuth, isAuthenticated, user } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [locked, setLocked] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Sessão ativa sem pendência → vai direto pro app
  // Sessão ativa COM must_change_password → limpa e exige novo login
  useEffect(() => {
    if (isAuthenticated) {
      if (user?.must_change_password) {
        clearAuth();
      } else {
        navigate(user?.role === "admin" ? "/settings/parametrization" : "/dashboard", { replace: true });
      }
    }
  }, []);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    try {
      const res = await api.post("/auth/login", data);
      const { access_token, refresh_token, user } = res.data;
      setAuth(user, access_token, refresh_token);

      if (user.must_change_password) {
        navigate("/change-password");
        return;
      }

      if (user.role === "admin") {
        navigate("/settings/parametrization");
      } else {
        navigate("/dashboard");
      }
    } catch (err: any) {
      const msg = err.response?.data?.message || "Credenciais inválidas.";
      if (msg.toLowerCase().includes("bloqueada")) setLocked(true);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-violet-600 flex items-center justify-center mb-3">
            <img src="/GPD.png" alt="GPD" className="w-12 h-12 object-contain" />
          </div>
          <h1 className="text-2xl font-bold text-white">GPD</h1>
          <p className="text-gray-500 text-sm mt-1">Governança Inteligente para Desenvolvimento</p>
        </div>

        {/* Form */}
        <div className="card">
          {locked && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
              Conta bloqueada por segurança após múltiplas tentativas incorretas. Aguarde 15 minutos antes de tentar novamente ou contate o administrador do sistema.
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">E-mail corporativo</label>
              <input
                {...register("email")}
                type="email"
                placeholder="voce@empresa.com"
                className="input-field"
                autoComplete="email"
              />
              {errors.email && <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Senha</label>
              <div className="relative">
                <input
                  {...register("password")}
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  className="input-field pr-10"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200"
                  tabIndex={-1}
                  aria-label={showPassword ? "Ocultar senha" : "Exibir senha"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
            </div>

            <button
              type="submit"
              disabled={loading || locked}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {loading ? (
                <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              ) : null}
              Entrar →
            </button>
          </form>

          <div className="mt-3 text-center">
            <a href="#" className="text-sm text-violet-400 hover:text-violet-300">
              Esqueci minha senha
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
