import { api } from "@/services/api";

export interface GeneratedComponent {
  id: string;
  design_component_id: string;
  component_name: string;
  target_framework: string;
  status: string;
  file_path: string | null;
  file_ext: string | null;
  todos_count: number;
  accessibility_warnings: string[];
  created_at: string;
  updated_at: string;
  code_content?: string;
  design_artifact_id?: string;
  repo_commit_sha?: string | null;
  repo_file_path?: string | null;
}

export interface TodoItem {
  line_number: number;
  content: string;
  priority: "high" | "medium" | "low";
}

export interface ComponentTodos {
  component_id: string;
  component_name: string;
  file_path: string | null;
  todos: TodoItem[];
  total_todos: number;
  high_priority: number;
  medium_priority: number;
  low_priority: number;
}

export const generatedFilesApi = {
  /**
   * List all generated components for a project
   */
  async listComponents(
    projectId: string,
    options?: {
      status?: string;
      target_framework?: string;
      limit?: number;
      offset?: number;
    }
  ) {
    const params = new URLSearchParams();
    if (options?.status) params.append("status", options.status);
    if (options?.target_framework) params.append("target_framework", options.target_framework);
    if (options?.limit) params.append("limit", String(options.limit));
    if (options?.offset) params.append("offset", String(options.offset));

    const response = await api.get(
      `/projects/${projectId}/components${params.toString() ? `?${params}` : ""}`
    );
    return response.data;
  },

  /**
   * Get a specific generated component with code content
   */
  async getComponent(projectId: string, componentId: string) {
    const response = await api.get(
      `/projects/${projectId}/components/${componentId}`
    );
    return response.data;
  },

  /**
   * Get all TODOs from a generated component
   */
  async getComponentTodos(
    projectId: string,
    componentId: string
  ): Promise<{ success: boolean; data: ComponentTodos }> {
    const response = await api.get(
      `/projects/${projectId}/components/${componentId}/todos`
    );
    return response.data;
  },

  /**
   * Update component code content
   */
  async updateComponent(
    projectId: string,
    componentId: string,
    codeContent: string
  ) {
    const response = await api.put(
      `/projects/${projectId}/components/${componentId}`,
      { code_content: codeContent }
    );
    return response.data;
  },

  /**
   * Generate component code for a specific framework
   */
  async generateComponent(
    projectId: string,
    componentId: string,
    targetFramework: string,
    description?: string
  ) {
    const response = await api.post(
      `/projects/${projectId}/components/${componentId}/generate`,
      {
        target_framework: targetFramework,
        description,
      }
    );
    return response.data;
  },

  /**
   * Generate all components in a design system
   */
  async generateAllComponents(
    projectId: string,
    artifactId: string,
    targetFramework: string
  ) {
    const response = await api.post(
      `/projects/${projectId}/components/design-systems/${artifactId}/generate-all`,
      null,
      {
        params: { target_framework: targetFramework },
      }
    );
    return response.data;
  },

  /**
   * Download component code as file
   */
  async downloadComponentCode(
    projectId: string,
    componentId: string,
    filename?: string
  ) {
    const component = await this.getComponent(projectId, componentId);
    const content = component.data.code_content;

    const element = document.createElement("a");
    const file = new Blob([content], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = filename || component.data.file_path || "generated-file.tsx";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  },
};
