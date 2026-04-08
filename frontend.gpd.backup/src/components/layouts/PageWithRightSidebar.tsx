import { ReactNode } from "react";
import { RightSidebar } from "@/components/layouts/RightSidebar";

interface PageWithRightSidebarProps {
  projectId: string;
  children: ReactNode;
  sidebarWidth?: string;
  showSidebar?: boolean;
}

/**
 * Wrapper component that adds a right sidebar with generated files panel to any page
 * Usage:
 * <PageWithRightSidebar projectId={projectId}>
 *   <YourPageContent />
 * </PageWithRightSidebar>
 */
export function PageWithRightSidebar({
  projectId,
  children,
  sidebarWidth = "w-80",
  showSidebar = true,
}: PageWithRightSidebarProps) {
  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Main content area */}
      <div className="flex-1 overflow-auto">
        {children}
      </div>

      {/* Right sidebar with generated files */}
      {showSidebar && (
        <RightSidebar
          projectId={projectId}
          width={sidebarWidth}
          show={showSidebar}
        />
      )}
    </div>
  );
}
