import { useState } from "react";
import { GeneratedFilesPanel } from "@/components/sidebars/GeneratedFilesPanel";
import { CodeEditor } from "@/components/sidebars/CodeEditor";

interface RightSidebarProps {
  projectId: string;
  width?: string;
  show?: boolean;
}

export function RightSidebar({
  projectId,
  width = "w-80",
  show = true,
}: RightSidebarProps) {
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [selectedComponentName, setSelectedComponentName] = useState<string>("");

  const handleEditComponent = (componentId: string, componentName: string) => {
    setSelectedComponentId(componentId);
    setSelectedComponentName(componentName);
  };

  if (!show) {
    return null;
  }

  return (
    <div
      className={`${width} flex flex-col border-l border-slate-700 bg-slate-900 overflow-hidden`}
    >
      {selectedComponentId ? (
        <CodeEditor
          projectId={projectId}
          componentId={selectedComponentId}
          componentName={selectedComponentName}
          onClose={() => setSelectedComponentId(null)}
        />
      ) : (
        <GeneratedFilesPanel
          projectId={projectId}
          onEditComponent={handleEditComponent}
        />
      )}
    </div>
  );
}
