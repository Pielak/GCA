import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectWizardPage } from "@/pages/ProjectWizardPage";
import { ArtifactsPage } from "@/pages/ArtifactsPage";
import { GatekeeperPage } from "@/pages/GatekeeperPage";
import { CodegenPage } from "@/pages/CodegenPage";
import { LegacyPage } from "@/pages/LegacyPage";
import { RoadmapPage } from "@/pages/RoadmapPage";
import { QAReadinessPage } from "@/pages/QAReadinessPage";
import { ParametrizationPage } from "@/pages/ParametrizationPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { AgentConfigPage } from "@/pages/AgentConfigPage";
import { RepoIntegrationsPage } from "@/pages/RepoIntegrationsPage";
import { RepositoryFilesPage } from "@/pages/RepositoryFilesPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { BackupRecoveryPage } from "@/pages/BackupRecoveryPage";
import { AdminProjectsPage } from "@/pages/AdminProjectsPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { ProjectTeamPage } from "@/pages/ProjectTeamPage";
import { ArguidorPage } from "@/pages/ArguidorPage";
import { MergePage } from "@/pages/MergePage";
import { ProposedModulesPage } from "@/pages/ProposedModulesPage";
import DocumentationPage from "@/pages/DocumentationPage";
import { GeneratedFilesPage } from "@/pages/GeneratedFilesPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Rotas públicas */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        {/* Rotas protegidas (dentro do AppShell com sidebar) */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/new" element={<ProjectWizardPage />} />
            <Route path="/projects/:projectId/artifacts" element={<ArtifactsPage />} />
            <Route path="/projects/:projectId/documentation" element={<DocumentationPage />} />
            <Route path="/projects/:projectId/generated-files" element={<GeneratedFilesPage />} />
            <Route path="/projects/:projectId/gatekeeper" element={<GatekeeperPage />} />
            <Route path="/projects/:projectId/arguidor" element={<ArguidorPage />} />
            <Route path="/projects/:projectId/codegen" element={<CodegenPage />} />
            <Route path="/projects/:projectId/legacy" element={<LegacyPage />} />
            <Route path="/projects/:projectId/roadmap" element={<RoadmapPage />} />
            <Route path="/projects/:projectId/merge" element={<MergePage />} />
            <Route path="/projects/:projectId/modules" element={<ProposedModulesPage />} />
            <Route path="/projects/:projectId/qa" element={<QAReadinessPage />} />
            <Route path="/projects/:projectId/agents" element={<AgentConfigPage />} />
            <Route path="/projects/:projectId/repos" element={<RepoIntegrationsPage />} />
            <Route path="/projects/:projectId/repos/:integrationId/files" element={<RepositoryFilesPage />} />
            <Route path="/projects/:projectId/notifications" element={<NotificationsPage />} />
            <Route path="/projects/:projectId/team" element={<ProjectTeamPage />} />
            <Route path="/settings/parametrization" element={<ParametrizationPage />} />
            <Route path="/settings/backup" element={<BackupRecoveryPage />} />
            <Route path="/admin/projects" element={<AdminProjectsPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
