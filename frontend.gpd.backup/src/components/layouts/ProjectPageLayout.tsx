import { ReactNode } from "react";
import { RightSidebar } from "@/components/layouts/RightSidebar";

interface ProjectPageLayoutProps {
  projectId: string;
  children: ReactNode;
  title?: string;
  subtitle?: string;
  showRightSidebar?: boolean;
}

/**
 * Standard project page layout with:
 * - Main content area (full width)
 * - Right sidebar with generated files panel
 * - Responsive design
 */
export function ProjectPageLayout({
  projectId,
  children,
  title,
  subtitle,
  showRightSidebar = true,
}: ProjectPageLayoutProps) {
  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-slate-950">
      {/* Page Header */}
      {title && (
        <div className="flex-shrink-0 border-b border-slate-700 bg-slate-900 px-6 py-4">
          <h1 className="text-2xl font-bold text-white">{title}</h1>
          {subtitle && <p className="text-sm text-slate-400 mt-1">{subtitle}</p>}
        </div>
      )}

      {/* Main content with sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Content area */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>

        {/* Right sidebar */}
        {showRightSidebar && (
          <RightSidebar
            projectId={projectId}
            width="w-96"
            show={showRightSidebar}
          />
        )}
      </div>
    </div>
  );
}
