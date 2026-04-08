import { createBrowserRouter } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
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
import { MergeEnginePage } from './pages/projects/MergeEnginePage';
import { ArguiderPage } from './pages/projects/ArguiderPage';
import { CodeGeneratorPage } from './pages/projects/CodeGeneratorPage';
import { QAReadinessPage } from './pages/projects/QAReadinessPage';
import { LegacyPage } from './pages/projects/LegacyPage';
import { RoadmapPage } from './pages/projects/RoadmapPage';
import { LiveDocsPage } from './pages/projects/LiveDocsPage';
import { QuestionnairePage } from './pages/projects/QuestionnairePage';
import { AcceptInvitationPage } from './pages/AcceptInvitationPage';
import { NovoProjetoPage } from './pages/NovoProjetoPage';
import { SetupWizardPage } from './pages/SetupWizardPage';

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
      { index: true, Component: AdminDashboardPage },
      { path: 'admin', Component: AdminDashboardPage },
      { path: 'admin/projects', Component: AdminProjectsPage },
      { path: 'admin/users', Component: AdminUsersPage },
      { path: 'admin/audit', Component: AdminAuditPage },
      { path: 'projects', Component: ProjectListPage },
      {
        path: 'projects/:id',
        Component: ProjectDetailLayout,
        children: [
          { index: true, Component: ProjectDashPage },
          { path: 'team', Component: ProjectTeamPage },
          { path: 'ocg', Component: OCGPage },
          { path: 'questionnaire', Component: QuestionnairePage },
          { path: 'ingestion', Component: IngestionPage },
          { path: 'gatekeeper', Component: GatekeeperPage },
          { path: 'merge', Component: MergeEnginePage },
          { path: 'arguider', Component: ArguiderPage },
          { path: 'codegen', Component: CodeGeneratorPage },
          { path: 'qa', Component: QAReadinessPage },
          { path: 'legacy', Component: LegacyPage },
          { path: 'roadmap', Component: RoadmapPage },
          { path: 'docs', Component: LiveDocsPage },
        ],
      },
    ],
  },
]);
