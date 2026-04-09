import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { RequireAdmin } from './components/guards/RequireAdmin';
import { useAuthStore } from './stores/authStore';
import { LoginPage } from './pages/LoginPage';
import { ResetPasswordPage } from './app/pages/auth/ResetPasswordPage';
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage';
import { AdminProjectsPage } from './pages/admin/AdminProjectsPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminAuditPage } from './pages/admin/AdminAuditPage';
import { ProjectListPage } from './pages/projects/ProjectListPage';
import { ProjectDetailLayout } from './pages/projects/ProjectDetailLayout';
import { ProjectDashPage } from './pages/projects/ProjectDashPage';
import { ProjectTeamPage } from './app/pages/projects/ProjectTeamPage';
import { OCGPage } from './pages/projects/OCGPage';
import { IngestionPage } from './pages/projects/IngestionPage';
import { GatekeeperPage } from './pages/projects/GatekeeperPage';
import { RepositoryPage } from './pages/projects/RepositoryPage';
import { RequireRepository } from './components/guards/RequireRepository';
import { ProjectSettingsPage } from './pages/projects/ProjectSettingsPage';
import { ExternalReposPage } from './pages/projects/ExternalReposPage';
import { ArguiderPage } from './pages/projects/ArguiderPage';
import { CodeGeneratorPage } from './pages/projects/CodeGeneratorPage';
import { QAReadinessPage } from './pages/projects/QAReadinessPage';
import { RoadmapPage } from './pages/projects/RoadmapPage';
import { LiveDocsPage } from './pages/projects/LiveDocsPage';
import { QuestionnairePage } from './pages/projects/QuestionnairePage';
import { AcceptInvitationPage } from './pages/AcceptInvitationPage';
import { NovoProjetoPage } from './pages/NovoProjetoPage';
import { SetupWizardPage } from './pages/SetupWizardPage';
import { TesterReviewPage } from './pages/projects/TesterReviewPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    Component: LoginPage,
  },
  {
    path: '/reset-password',
    Component: ResetPasswordPage,
  },
  {
    path: '/accept-invitation',
    Component: AcceptInvitationPage,
  },
  {
    path: '/novo-projeto',
    Component: NovoProjetoPage,
  },
  {
    path: '/setup',
    Component: SetupWizardPage,
  },
  {
    path: '/',
    Component: AppLayout,
    children: [
      // Rota index: redireciona admin para /admin, outros para /projects
      { index: true, element: <IndexRedirect /> },
      // Admin routes — protegidas por RequireAdmin
      {
        path: 'admin',
        element: <RequireAdmin><AdminDashboardPage /></RequireAdmin>,
      },
      {
        path: 'admin/projects',
        element: <RequireAdmin><AdminProjectsPage /></RequireAdmin>,
      },
      {
        path: 'admin/users',
        element: <RequireAdmin><AdminUsersPage /></RequireAdmin>,
      },
      {
        path: 'admin/audit',
        element: <RequireAdmin><AdminAuditPage /></RequireAdmin>,
      },
      { path: 'projects', Component: ProjectListPage },
      {
        path: 'projects/:id',
        Component: ProjectDetailLayout,
        children: [
          { index: true, Component: ProjectDashPage },
          { path: 'team', Component: ProjectTeamPage },
          { path: 'ocg', Component: OCGPage },
          { path: 'questionnaire', Component: QuestionnairePage },
          { path: 'repository', Component: RepositoryPage },
          { path: 'external-repos', element: <RequireRepository><ExternalReposPage /></RequireRepository> },
          { path: 'ingestion', element: <RequireRepository><IngestionPage /></RequireRepository> },
          { path: 'gatekeeper', element: <RequireRepository><GatekeeperPage /></RequireRepository> },
          { path: 'arguider', element: <RequireRepository><ArguiderPage /></RequireRepository> },
          { path: 'codegen', element: <RequireRepository><CodeGeneratorPage /></RequireRepository> },
          { path: 'qa', element: <RequireRepository><QAReadinessPage /></RequireRepository> },
          { path: 'tester-review', element: <RequireRepository><TesterReviewPage /></RequireRepository> },
          { path: 'roadmap', element: <RequireRepository><RoadmapPage /></RequireRepository> },
          { path: 'docs', element: <RequireRepository><LiveDocsPage /></RequireRepository> },
          { path: 'settings', Component: ProjectSettingsPage },
        ],
      },
    ],
  },
]);

/**
 * Redireciona a rota "/" com base no papel do usuário:
 * - Admin → /admin
 * - Outros → /projects
 */
function IndexRedirect() {
  const user = useAuthStore((s) => s.user);

  if (user?.is_admin) {
    return <Navigate to="/admin" replace />;
  }
  return <Navigate to="/projects" replace />;
}
