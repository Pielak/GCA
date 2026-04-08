/**
 * TestCaseEditor — Modal para editar casos de teste
 */

import { useState } from 'react';
import { X, Plus, Trash2, Save } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useMutation } from '@tanstack/react-query';
import { api } from '@/services/api';

interface TestCase {
  id: string;
  name: string;
  description: string;
  preconditions: string;
  steps: string[];
  expected_result: string;
}

interface TestCaseEditorProps {
  projectId: string;
  testType: string;
  testId?: string;
  isOpen: boolean;
  onClose: () => void;
  onSave: () => void;
}

export function TestCaseEditor({
  projectId,
  testType,
  testId,
  isOpen,
  onClose,
  onSave,
}: TestCaseEditorProps) {
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);
  const [newStep, setNewStep] = useState('');

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!testId) return;
      // TODO: Implement in backend
      return api.put(`/projects/${projectId}/qa/tests/${testId}`, {
        test_cases: testCases,
      });
    },
    onSuccess: () => {
      toast.success('Testes salvos com sucesso');
      onSave();
    },
    onError: () => {
      toast.error('Erro ao salvar testes');
    },
  });

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-dark-100 rounded-lg border border-gray-700 max-w-2xl w-full max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 flex items-center justify-between p-4 border-b border-gray-700 bg-dark-100">
          <div>
            <h2 className="text-lg font-semibold text-white capitalize">
              Editar {testType} testes
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Customize os casos de teste para suas necessidades
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-300 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {testCases.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-gray-500 text-sm">Nenhum caso de teste carregado</p>
              <p className="text-xs text-gray-600 mt-2">
                Os casos de teste serão carregados quando você abrir este editor
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {testCases.map((testCase, idx) => (
                <div
                  key={testCase.id}
                  className="border border-gray-700 rounded-lg p-4 bg-dark-200"
                >
                  {/* Test Case Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <input
                        type="text"
                        value={testCase.name}
                        onChange={(e) => {
                          const updated = [...testCases];
                          updated[idx].name = e.target.value;
                          setTestCases(updated);
                        }}
                        className="text-sm font-medium text-gray-300 bg-dark border border-gray-700 rounded px-2 py-1 w-full"
                        placeholder="Nome do caso de teste"
                      />
                    </div>
                    <button
                      onClick={() => {
                        setTestCases(testCases.filter((_, i) => i !== idx));
                      }}
                      className="text-red-400 hover:text-red-300 ml-2 shrink-0"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  {/* Description */}
                  <div className="space-y-2 mb-3">
                    <label className="text-xs text-gray-400">Descrição</label>
                    <textarea
                      value={testCase.description}
                      onChange={(e) => {
                        const updated = [...testCases];
                        updated[idx].description = e.target.value;
                        setTestCases(updated);
                      }}
                      className="text-xs text-gray-300 bg-dark border border-gray-700 rounded px-2 py-1 w-full h-12 resize-none"
                      placeholder="Descrição do caso de teste"
                    />
                  </div>

                  {/* Preconditions */}
                  <div className="space-y-2 mb-3">
                    <label className="text-xs text-gray-400">Pré-condições</label>
                    <textarea
                      value={testCase.preconditions}
                      onChange={(e) => {
                        const updated = [...testCases];
                        updated[idx].preconditions = e.target.value;
                        setTestCases(updated);
                      }}
                      className="text-xs text-gray-300 bg-dark border border-gray-700 rounded px-2 py-1 w-full h-10 resize-none"
                      placeholder="Condições necessárias antes de executar"
                    />
                  </div>

                  {/* Expected Result */}
                  <div className="space-y-2">
                    <label className="text-xs text-gray-400">Resultado Esperado</label>
                    <textarea
                      value={testCase.expected_result}
                      onChange={(e) => {
                        const updated = [...testCases];
                        updated[idx].expected_result = e.target.value;
                        setTestCases(updated);
                      }}
                      className="text-xs text-gray-300 bg-dark border border-gray-700 rounded px-2 py-1 w-full h-10 resize-none"
                      placeholder="Resultado esperado ao executar o teste"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex items-center justify-end gap-2 p-4 border-t border-gray-700 bg-dark-100">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 hover:bg-dark-200 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || testCases.length === 0}
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors',
              saveMutation.isPending || testCases.length === 0
                ? 'bg-emerald-600/50 text-gray-400 cursor-not-allowed'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            )}
          >
            <Save size={14} />
            {saveMutation.isPending ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );
}
