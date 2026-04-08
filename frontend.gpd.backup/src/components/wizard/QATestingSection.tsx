/**
 * QATestingSection — Seção para gerenciamento automático de testes
 *
 * Funcionalidades:
 * - Exibir testes automáticos (gerados ao fazer upload de artefatos)
 * - Agrupar testes por tipo: Unit, Integration, Component, E2E, Responsive
 * - [✎ Editar] test cases para cada tipo
 * - [⊘ Desativar] testes que não são relevantes
 * - Tech Stack detection (via StackShare)
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  TestTube2,
  AlertTriangle,
  CheckCircle2,
  Loader,
  ChevronDown,
  ChevronUp,
  Edit2,
  Circle,
  CheckCircle,
  type LucideIcon,
} from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { languageStackApi, type TestDocument } from '@/services/languageStackApi';
import { HelpIcon } from '@/components/HelpIcon';
import { api } from '@/services/api';
import { TechStackSection } from '@/components/qa/TechStackSection';
import { TestCaseEditor } from '@/components/qa/TestCaseEditor';

interface QATestingSectionProps {
  projectId: string;
  isLocked?: boolean;
}

interface ExpandedTests {
  [testType: string]: boolean;
}

interface TestGroup {
  type: 'unit' | 'integration';
  label: string;
  description: string;
  icon: LucideIcon;
  tests: TestDocument[];
  enabled: boolean;
  color: 'blue' | 'green';
}

interface EditModalState {
  open: boolean;
  testType?: string;
  testId?: string;
}

export function QATestingSection({
  projectId,
  isLocked = false,
}: QATestingSectionProps) {
  const queryClient = useQueryClient();
  const [expandedTests, setExpandedTests] = useState<ExpandedTests>({});
  const [editModal, setEditModal] = useState<EditModalState>({ open: false });
  const [disabledTests, setDisabledTests] = useState<Set<string>>(new Set());

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: tests, isLoading: testsLoading } = useQuery<{
    project_id: string;
    test_documents: TestDocument[];
    total: number
  }>({
    queryKey: ['test-documents', projectId],
    queryFn: () => languageStackApi.listTestDocuments(projectId),
    enabled: !isLocked,
  });

  // ── Mutations ──────────────────────────────────────────────────────────

  const toggleTestMutation = useMutation({
    mutationFn: async (testId: string) => {
      // API call to toggle test enabled/disabled
      // TODO: implement in backend
      return Promise.resolve();
    },
    onSuccess: () => {
      toast.success('Teste atualizado');
      queryClient.invalidateQueries({ queryKey: ['test-documents', projectId] });
    },
    onError: () => {
      toast.error('Erro ao atualizar teste');
    },
  });

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleToggleExpand = (testType: string) => {
    setExpandedTests(prev => ({
      ...prev,
      [testType]: !prev[testType],
    }));
  };

  const handleDisableTest = (testId: string) => {
    setDisabledTests(prev => {
      const newSet = new Set(prev);
      if (newSet.has(testId)) {
        newSet.delete(testId);
      } else {
        newSet.add(testId);
      }
      return newSet;
    });
    toggleTestMutation.mutate(testId);
  };

  const handleEditTest = (testType: string, testId: string) => {
    setEditModal({ open: true, testType, testId });
  };

  // ── Group Tests by Type ────────────────────────────────────────────────

  const groupTests = (): TestGroup[] => {
    const allTests = tests?.test_documents || [];

    const typeMap: Record<string, TestGroup> = {
      unit: {
        type: 'unit',
        label: 'Testes Unitários',
        description: 'Testes de unidades isoladas de código',
        icon: TestTube2,
        tests: allTests.filter(t => t.type === 'unit'),
        enabled: true,
        color: 'blue',
      },
      integration: {
        type: 'integration',
        label: 'Testes Integrados',
        description: 'Testes de integração entre módulos',
        icon: TestTube2,
        tests: allTests.filter(t => t.type === 'integration'),
        enabled: true,
        color: 'green',
      },
    };

    return Object.values(typeMap).filter(group => group.tests.length > 0);
  };

  const testGroups = groupTests();

  const getColorClasses = (color: 'blue' | 'green') => {
    const colors: Record<string, { bg: string; border: string; text: string; icon: string }> = {
      blue: { bg: 'bg-blue-900/20', border: 'border-blue-700/30', text: 'text-blue-300', icon: 'text-blue-400' },
      green: { bg: 'bg-green-900/20', border: 'border-green-700/30', text: 'text-green-300', icon: 'text-green-400' },
    };
    return colors[color];
  };

  // ── Render ─────────────────────────────────────────────────────────────

  if (isLocked) {
    return (
      <div className="bg-dark-100 rounded-xl border border-gray-800 p-5 opacity-50 pointer-events-none">
        <div className="flex items-center gap-2 text-gray-500 font-semibold mb-4">
          <TestTube2 size={15} />
          <span>QA Readiness</span>
          <span className="text-xs text-gray-600 ml-1">Selecione a linguagem primeiro</span>
        </div>
      </div>
    );
  }

  return (
    <section className="bg-dark-100 rounded-xl border border-gray-800 p-5">
      {/* Header */}
      <div className="flex items-center gap-2 text-white font-semibold mb-4">
        <TestTube2 size={15} className="text-violet-400" />
        <span>QA Readiness</span>
        <HelpIcon text="Testes são gerados automaticamente quando você faz upload de artefatos (design systems, código, modelos de dados). Você pode editar, desativar ou executar qualquer teste." />
      </div>

      {/* Auto-Generated Notice */}
      <div className="mb-6 p-4 bg-violet-900/20 border border-violet-700/30 rounded-lg">
        <div className="flex items-start gap-2">
          <CheckCircle2 size={16} className="text-violet-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-violet-300">Testes Automáticos</p>
            <p className="text-xs text-gray-400 mt-1">
              Estes testes foram gerados automaticamente baseados nos artefatos do seu projeto. Você pode editá-los ou desativá-los conforme necessário.
            </p>
          </div>
        </div>
      </div>

      {/* Tests by Type */}
      {testsLoading ? (
        <div className="flex items-center justify-center py-12 text-gray-500">
          <Loader size={20} className="animate-spin mr-2" />
          Carregando testes…
        </div>
      ) : testGroups.length === 0 ? (
        <div className="py-12 text-center">
          <TestTube2 size={40} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">Nenhum teste ainda</p>
          <p className="text-sm text-gray-600 mt-2">
            Testes serão gerados automaticamente quando você fizer upload de artefatos.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {testGroups.map(group => {
            const colors = getColorClasses(group.color);
            const isExpanded = expandedTests[group.type];
            const enabledCount = group.tests.filter(t => !disabledTests.has(t.id)).length;

            return (
              <div key={group.type} className={clsx('rounded-lg border', colors.border, colors.bg)}>
                {/* Group Header */}
                <button
                  onClick={() => handleToggleExpand(group.type)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:opacity-80 transition-opacity"
                >
                  <div className="flex items-center gap-3 flex-1 text-left">
                    <CheckCircle2 size={16} className={colors.icon} />
                    <div className="min-w-0">
                      <p className={clsx('text-sm font-medium', colors.text)}>
                        {group.label}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {enabledCount} de {group.tests.length} testes ativos
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-gray-400">
                    <span className="text-xs font-medium">{group.tests.length}</span>
                    {isExpanded ? (
                      <ChevronUp size={16} />
                    ) : (
                      <ChevronDown size={16} />
                    )}
                  </div>
                </button>

                {/* Expanded Content */}
                {isExpanded && (
                  <div className="border-t border-current border-opacity-20 px-4 py-3 space-y-3">
                    {/* Action Buttons */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleEditTest(group.type, group.tests[0]?.id || '')}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-200 hover:bg-dark/80 rounded text-xs font-medium text-gray-300 transition-colors"
                      >
                        <Edit2 size={12} />
                        Editar
                      </button>
                      <button
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-200 hover:bg-dark/80 rounded text-xs font-medium text-gray-300 transition-colors"
                      >
                        <CheckCircle size={12} />
                        Executar
                      </button>
                    </div>

                    {/* Test Items */}
                    <div className="space-y-2">
                      {group.tests.map(test => {
                        const isDisabled = disabledTests.has(test.id);
                        return (
                          <div
                            key={test.id}
                            className={clsx(
                              'flex items-start gap-2 p-2.5 rounded bg-dark/40 transition-opacity',
                              isDisabled && 'opacity-50'
                            )}
                          >
                            <button
                              onClick={() => handleDisableTest(test.id)}
                              className="text-gray-400 hover:text-gray-300 mt-0.5 shrink-0"
                              title={isDisabled ? 'Ativar teste' : 'Desativar teste'}
                            >
                              {isDisabled ? (
                                <Circle size={14} />
                              ) : (
                                <CheckCircle size={14} className="text-emerald-400" />
                              )}
                            </button>
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium text-gray-300 capitalize">
                                {test.objective || `${test.type} test`}
                              </p>
                              <p className="text-xs text-gray-500 mt-0.5">
                                {test.test_cases_count || 0} casos de teste
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tech Stack Section */}
      <div className="mt-8 border-t border-gray-700 pt-8">
        <TechStackSection projectId={projectId} />
      </div>

      {/* Test Case Editor Modal */}
      {editModal.open && (
        <TestCaseEditor
          projectId={projectId}
          testType={editModal.testType || ''}
          isOpen={editModal.open}
          onClose={() => setEditModal({ open: false })}
          onSave={() => {
            setEditModal({ open: false });
            queryClient.invalidateQueries({ queryKey: ['test-documents', projectId] });
          }}
        />
      )}
    </section>
  );
}
