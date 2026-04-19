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
import { AdminMetricsPage } from './pages/admin/AdminMetricsPage';
import { AdminBackupsPage } from './pages/admin/AdminBackupsPage';
import { AdminIncidentsPage } from './pages/admin/AdminIncidentsPage';
import { AdminSupportPage } from './pages/admin/AdminSupportPage';
import { AdminReleasesPage } from './pages/admin/AdminReleasesPage';
import { AdminReleaseDetailPage } from './pages/admin/AdminReleaseDetailPage';
import { ReleasesPage } from './pages/ReleasesPage';
import { ProjectBackupPage } from './pages/projects/ProjectBackupPage';
import { AdminProjectViewPage } from './pages/admin/AdminProjectViewPage';
import { DesignShowcasePage } from './pages/DesignShowcasePage';
import { ProjectListPage } from './pages/projects/ProjectListPage';
import { ProjectDetailLayout } from './pages/projects/ProjectDetailLayout';
import { ProjectDashPage } from './pages/projects/ProjectDashPage';
import { ProjectTeamPage } from './app/pages/projects/ProjectTeamPage';
import { OCGPage } from './pages/projects/OCGPage';
import { IngestionPage } from './pages/projects/IngestionPage';
import { GatekeeperPage } from './pages/projects/GatekeeperPage';
import { BacklogPage } from './pages/projects/BacklogPage';
import { RequireProjectSetup } from './components/guards/RequireProjectSetup';
import { ProjectSettingsPage } from './pages/projects/ProjectSettingsPage';
import { ExternalReposPage } from './pages/projects/ExternalReposPage';
import { ArguiderPage } from './pages/projects/ArguiderPage';
import { CodeGeneratorPage } from './pages/projects/CodeGeneratorPage';
import { QAReadinessPage } from './pages/projects/QAReadinessPage';
import { RoadmapPage } from './pages/projects/RoadmapPage';
import { LiveDocsPage } from './pages/projects/LiveDocsPage';
import { ReadinessPage } from './pages/projects/ReadinessPage';
import { AcceptInvitationPage } from './pages/AcceptInvitationPage';
import { SolicitarProjetoPage } from './pages/SolicitarProjetoPage';
import { SetupWizardPage } from './pages/SetupWizardPage';
import { TesterReviewPage } from './pages/projects/TesterReviewPage';
import { PipelineAuditPage } from './pages/projects/PipelineAuditPage';
import { ProjectLoginPage } from './pages/ProjectLoginPage';
import { IncidentListPage } from './pages/projects/IncidentListPage';
import { IncidentDetailPage } from './pages/projects/IncidentDetailPage';
import { ProjectMetricsPage } from './pages/projects/ProjectMetricsPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    Component: LoginPage,
  },
  {
    path: '/p/:slug',
    Component: ProjectLoginPage,
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
    // DT-017: caminho antigo redireciona para o wizard canônico /solicitar-projeto.
    // Mantido como Navigate para não quebrar links em emails/histórico de navegação.
    path: '/novo-projeto',
    element: <Navigate to="/solicitar-projeto" replace />,
  },
  {
    path: '/solicitar-projeto',
    Component: SolicitarProjetoPage,
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
        path: 'admin/projects/:id',
        element: <RequireAdmin><AdminProjectViewPage /></RequireAdmin>,
      },
      {
        path: 'admin/users',
        element: <RequireAdmin><AdminUsersPage /></RequireAdmin>,
      },
      {
        path: 'admin/audit',
        element: <RequireAdmin><AdminAuditPage /></RequireAdmin>,
      },
      {
        path: 'admin/metrics',
        element: <RequireAdmin><AdminMetricsPage /></RequireAdmin>,
      },
      {
        path: 'admin/backups',
        element: <RequireAdmin><AdminBackupsPage /></RequireAdmin>,
      },
      {
        path: 'admin/incidents',
        element: <RequireAdmin><AdminIncidentsPage /></RequireAdmin>,
      },
      {
        path: 'admin/support',
        element: <RequireAdmin><AdminSupportPage /></RequireAdmin>,
      },
      {
        path: 'admin/releases',
        element: <RequireAdmin><AdminReleasesPage /></RequireAdmin>,
      },
      {
        path: 'admin/releases/:releaseId',
        element: <RequireAdmin><AdminReleaseDetailPage /></RequireAdmin>,
      },
      { path: 'releases', Component: ReleasesPage },
      {
        path: 'design-showcase',
        element: <RequireAdmin><DesignShowcasePage /></RequireAdmin>,
      },
      { path: 'projects', Component: ProjectListPage },
      {
        path: 'projects/:id',
        Component: ProjectDetailLayout,
        children: [
          { index: true, element: <RequireProjectSetup><ProjectDashPage /></RequireProjectSetup> },
          { path: 'team', Component: ProjectTeamPage },
          { path: 'ocg', Component: OCGPage },
          // Rotas antigas redirecionam para /settings?tab=... (consolidação).
          // Preserva bookmarks, links de email e a SetupChecklist não quebra
          // se alguém acertar /questionnaire ou /repository direto.
          { path: 'questionnaire', element: <Navigate to="../settings?tab=questionario" replace /> },
          { path: 'repository', element: <Navigate to="../settings?tab=repo" replace /> },
          { path: 'external-repos', Component: ExternalReposPage },
          { path: 'ingestion', element: <RequireProjectSetup><IngestionPage /></RequireProjectSetup> },
          { path: 'gatekeeper', element: <RequireProjectSetup><GatekeeperPage /></RequireProjectSetup> },
          { path: 'arguider', element: <RequireProjectSetup><ArguiderPage /></RequireProjectSetup> },
          { path: 'codegen', element: <RequireProjectSetup><CodeGeneratorPage /></RequireProjectSetup> },
          // Alias: URL antiga /code-generator redireciona pro path canônico /codegen.
          // Mantido para não quebrar bookmarks/emails que ainda apontam pra cá.
          { path: 'code-generator', element: <Navigate to="../codegen" replace /> },
          { path: 'qa', element: <RequireProjectSetup><QAReadinessPage /></RequireProjectSetup> },
          { path: 'tester-review', element: <RequireProjectSetup><TesterReviewPage /></RequireProjectSetup> },
          { path: 'backlog', element: <RequireProjectSetup><BacklogPage /></RequireProjectSetup> },
          { path: 'roadmap', element: <RequireProjectSetup><RoadmapPage /></RequireProjectSetup> },
          { path: 'docs', element: <RequireProjectSetup><LiveDocsPage /></RequireProjectSetup> },
          { path: 'readiness', element: <RequireProjectSetup><ReadinessPage /></RequireProjectSetup> },
          { path: 'settings', Component: ProjectSettingsPage },
          { path: 'audit', Component: PipelineAuditPage },
          { path: 'backups', Component: ProjectBackupPage },
          { path: 'incidents', Component: IncidentListPage },
          { path: 'incidents/:ticketId', Component: IncidentDetailPage },
          { path: 'metrics', Component: ProjectMetricsPage },
        ],
      },
    ],
  },
]);

/**
 * Redireciona a rota "/" com base no papel do usuário:
 * - Admin sem projetos como membro → /admin
 * - Admin com projetos como membro → /projects (com link admin no header)
 * - Outros → /projects
 */
function IndexRedirect() {
  const user = useAuthStore((s) => s.user);

  if (user?.is_admin) {
    const hasMemberships = user.project_roles && user.project_roles.length > 0;
    if (!hasMemberships) {
      return <Navigate to="/admin" replace />;
    }
  }
  return <Navigate to="/projects" replace />;
}
