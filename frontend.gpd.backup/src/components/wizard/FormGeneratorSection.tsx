/**
 * FormGeneratorSection — Phase 4 Sprint 3 — Form Component Generation UI
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { FileText, Loader, Plus, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';
import { api } from '@/services/api';

interface FormGeneratorSectionProps {
  projectId: string;
  isLocked?: boolean;
}

interface FormField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder: string;
}

interface FormTemplate {
  name: string;
  description: string;
  fields: FormField[];
}

export function FormGeneratorSection({
  projectId,
  isLocked = false,
}: FormGeneratorSectionProps) {
  const [selectedTemplate, setSelectedTemplate] = useState<string>('login');
  const [formName, setFormName] = useState('LoginForm');
  const [validationLib, setValidationLib] = useState<'zod' | 'yup'>('zod');
  const [customFields, setCustomFields] = useState<FormField[]>([]);
  const [useTemplate, setUseTemplate] = useState(true);

  // Fetch field types
  const { data: fieldTypesData } = useQuery({
    queryKey: ['form-field-types', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/forms/field-types`);
      return res.data;
    },
    enabled: !isLocked,
  });

  // Fetch templates
  const { data: templatesData } = useQuery({
    queryKey: ['form-templates', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}/forms/templates`);
      return res.data.data;
    },
    enabled: !isLocked,
  });

  // Generate form
  const { data: generationData, isPending, mutate: generateForm } = useMutation({
    mutationFn: async () => {
      const fields = useTemplate && templatesData
        ? templatesData[selectedTemplate]?.fields || []
        : customFields;

      const res = await api.post(`/projects/${projectId}/forms/generate`, {
        form_name: formName,
        fields,
        framework: 'react',
        validation_lib: validationLib,
        include_api_integration: true,
      });
      return res.data;
    },
  });

  const addCustomField = () => {
    setCustomFields([
      ...customFields,
      {
        name: `field${customFields.length}`,
        label: 'Field Label',
        type: 'text',
        required: false,
        placeholder: '',
      },
    ]);
  };

  const removeCustomField = (idx: number) => {
    setCustomFields(customFields.filter((_, i) => i !== idx));
  };

  if (isLocked) {
    return (
      <div className="text-xs text-gray-500">
        Gerador de forms estará disponível quando o Gatekeeper estiver aprovado.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold">
        <FileText size={15} className="text-blue-400" />
        <span>Form Generator (Phase 4 Sprint 3)</span>
      </div>

      {/* Use Template Toggle */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="useTemplate"
          checked={useTemplate}
          onChange={(e) => setUseTemplate(e.target.checked)}
          className="rounded border-gray-700"
        />
        <label htmlFor="useTemplate" className="text-xs text-gray-400">
          Usar template pré-construído
        </label>
      </div>

      {/* Template Selection or Form Name */}
      {useTemplate && templatesData ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">Escolha um template:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {Object.entries(templatesData).map(([key, template]: any) => (
              <button
                key={key}
                onClick={() => {
                  setSelectedTemplate(key);
                  setFormName(template.name);
                }}
                className={clsx(
                  'p-3 rounded-lg border text-xs transition-all text-left',
                  selectedTemplate === key
                    ? 'bg-blue-600/30 border-blue-600 text-blue-300'
                    : 'bg-gray-800/30 border-gray-700 text-gray-400 hover:border-gray-600'
                )}
              >
                <p className="font-medium">{template.name}</p>
                <p className="text-gray-500 text-xs mt-1">{template.description}</p>
                <p className="text-gray-600 text-xs mt-1">{template.fields.length} campos</p>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Nome do Form:</label>
          <input
            type="text"
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="LoginForm"
            className="w-full px-3 py-2 bg-dark-200 border border-gray-700 rounded text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      )}

      {/* Validation Library */}
      <div className="space-y-2">
        <p className="text-xs text-gray-400">Biblioteca de validação:</p>
        <div className="flex gap-2">
          {(['zod', 'yup'] as const).map((lib) => (
            <button
              key={lib}
              onClick={() => setValidationLib(lib)}
              className={clsx(
                'flex-1 px-3 py-2 rounded text-xs transition-colors border',
                validationLib === lib
                  ? 'bg-blue-600/30 border-blue-600 text-blue-300'
                  : 'bg-gray-800/30 border-gray-700 text-gray-400 hover:border-gray-600'
              )}
            >
              {lib === 'zod' ? 'Zod (Type-first)' : 'Yup (Simple)'}
            </button>
          ))}
        </div>
      </div>

      {/* Custom Fields */}
      {!useTemplate && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">Campos customizados:</p>
            <button
              onClick={addCustomField}
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              <Plus size={12} />
              Adicionar
            </button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {customFields.map((field, idx) => (
              <div key={idx} className="flex gap-2 items-start">
                <input
                  type="text"
                  value={field.name}
                  onChange={(e) => {
                    const newFields = [...customFields];
                    newFields[idx].name = e.target.value;
                    setCustomFields(newFields);
                  }}
                  placeholder="fieldName"
                  className="flex-1 px-2 py-1 bg-dark-200 border border-gray-700 rounded text-white text-xs"
                />
                <select
                  value={field.type}
                  onChange={(e) => {
                    const newFields = [...customFields];
                    newFields[idx].type = e.target.value;
                    setCustomFields(newFields);
                  }}
                  className="px-2 py-1 bg-dark-200 border border-gray-700 rounded text-white text-xs"
                >
                  <option value="text">Text</option>
                  <option value="email">Email</option>
                  <option value="password">Password</option>
                  <option value="textarea">Textarea</option>
                  <option value="select">Select</option>
                  <option value="checkbox">Checkbox</option>
                </select>
                <button
                  onClick={() => removeCustomField(idx)}
                  className="text-red-400 hover:text-red-300"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Generate Button */}
      <button
        onClick={() => generateForm()}
        disabled={isPending || !formName}
        className={clsx(
          'w-full px-4 py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-colors',
          isPending || !formName
            ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700 text-white'
        )}
      >
        {isPending ? (
          <>
            <Loader size={14} className="animate-spin" />
            Gerando form...
          </>
        ) : (
          <>
            <FileText size={14} />
            Gerar Form Component
          </>
        )}
      </button>

      {/* Results */}
      {generationData && (
        <div className="space-y-4 border-t border-gray-700 pt-4">
          <div className="bg-dark-200/50 border border-blue-700/30 rounded-lg p-3">
            <p className="text-xs text-blue-300">
              ✅ <strong>{generationData.form_name}</strong> gerado com sucesso
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {generationData.fields.length} campos • {validationLib.toUpperCase()} validation
            </p>
          </div>

          {/* Generated Files */}
          <div>
            <p className="text-xs text-gray-400 mb-2 font-semibold">Arquivos Gerados</p>
            <div className="space-y-2">
              {generationData.form_component && (
                <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                  <p className="text-sm font-medium text-gray-300">
                    {generationData.form_component.file}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Componente React com validação automática
                  </p>
                </div>
              )}
              {generationData.validation_schema && (
                <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                  <p className="text-sm font-medium text-gray-300">
                    {generationData.validation_schema.file}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Schema de validação {validationLib.toUpperCase()}
                  </p>
                </div>
              )}
              {generationData.types && (
                <div className="bg-dark-200/30 border border-gray-700/30 rounded-lg p-3">
                  <p className="text-sm font-medium text-gray-300">
                    {generationData.types.file}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    TypeScript type definitions
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
