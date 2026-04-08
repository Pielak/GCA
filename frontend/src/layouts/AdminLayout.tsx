import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Lock, LogOut, Menu, X, BarChart3, Users, AlertCircle, Ticket, Bell, Settings, Package, Sliders } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

export const AdminLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const navigate = useNavigate()
  const location = useLocation()
  const { logout, user } = useAuth()

  const menuItems = [
    { path: '/admin/dashboard', icon: BarChart3, label: 'Dashboard', name: 'dashboard' },
    { path: '/admin/settings', icon: Sliders, label: 'Parametrização', name: 'settings' },
    { path: '/admin/projects', icon: Package, label: 'Projetos', name: 'projects' },
    { path: '/admin/users', icon: Users, label: 'Usuários', name: 'users' },
    { path: '/admin/security', icon: AlertCircle, label: 'Segurança', name: 'security' },
    { path: '/admin/tickets', icon: Ticket, label: 'Tickets', name: 'tickets' },
    { path: '/admin/integrations', icon: Bell, label: 'Integrações', name: 'integrations' },
    { path: '/admin/alerts', icon: Settings, label: 'Alertas', name: 'alerts' },
  ]

  const isActive = (path: string) => location.pathname === path

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Mobile Menu Button */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-gray-800 border-b border-gray-700 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img src="/images/gca-icon-40.png" alt="GCA" className="w-8 h-8" />
          <span className="font-bold text-white">GCA</span>
        </div>
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="text-gray-400 hover:text-white"
        >
          {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-screen bg-gray-800 border-r border-gray-700 transition-all duration-300 ${
          sidebarOpen ? 'w-64' : 'w-0'
        } overflow-hidden lg:w-64 pt-20 lg:pt-0 z-40`}
      >
        <div className="hidden lg:flex items-center gap-3 px-6 py-6 border-b border-gray-700">
          <img src="/images/gca-icon-40.png" alt="GCA" className="w-10 h-10" />
          <h1 className="text-xl font-bold text-white">GCA</h1>
        </div>

        <nav className="px-4 py-8 space-y-2">
          {menuItems.map((item) => (
            <button
              key={item.name}
              onClick={() => {
                navigate(item.path)
                setSidebarOpen(false)
              }}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition ${
                isActive(item.path)
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              <item.icon size={20} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 lg:hidden z-30"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 sticky top-0 z-20 lg:ml-64 mt-16 lg:mt-0">
        <div className="px-6 py-4 flex items-center justify-between">
          <div className="hidden lg:block">
            <h2 className="text-xl font-semibold text-white">Admin Dashboard</h2>
          </div>
          <div className="flex items-center gap-4 ml-auto">
            {user && (
              <div className="flex items-center gap-2">
                <div className="text-right">
                  <p className="text-sm font-medium text-white">{user.full_name}</p>
                  <p className="text-xs text-gray-400">{user.email}</p>
                </div>
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full" />
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 text-gray-400 hover:text-white transition px-3 py-2 rounded-lg hover:bg-gray-700"
            >
              <LogOut size={18} />
              <span className="hidden sm:inline text-sm">Sair</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="lg:ml-64 pt-4">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
