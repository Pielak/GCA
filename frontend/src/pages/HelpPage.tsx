import { useState, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, BookOpen, ChevronRight, Loader2, HelpCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

// MVP 18 Fase 18.1 — HelpPage skeleton.
// Layout 3 colunas: TOC (esquerda) + conteúdo (centro) + search (topo centro).
// Em 18.1 o conteúdo é placeholder; endpoints reais chegam em 18.2,
// conteúdo real em 18.3, busca FTS5 em 18.4, renderer markdown em 18.5.
//
// Rotas que apontam aqui:
// - /admin/help (Admin)
// - /projects/:id/help (GP/Dev/Tester/QA membro do projeto)
//
// Stub do TOC hardcoded aqui (10 capítulos canônicos propostos no plan).
// Vai virar fetch de /api/v1/help/toc em 18.2.

interface TocChapter {
  id: string
  title: string
  order: number
}

interface HelpSection {
  id: string
  title: string
  markdown: string
}

const STUB_TOC: TocChapter[] = [
  { id: '01-visao-geral', title: 'Visão geral & Glossário', order: 1 },
  { id: '02-instalacao', title: 'Instalação & primeiro setup', order: 2 },
  { id: '03-rbac', title: 'RBAC e papéis', order: 3 },
  { id: '04-pipeline', title: 'Pipeline canônico do GCA', order: 4 },
  { id: '05-ocg', title: 'OCG — Objeto de Contexto Global', order: 5 },
  { id: '06-admin', title: 'Área Administrativa', order: 6 },
  { id: '07-gp', title: 'Área de Gestão de Projeto', order: 7 },
  { id: '08-codegen', title: 'Codegen e linguagens suportadas', order: 8 },
  { id: '09-observabilidade', title: 'Observabilidade', order: 9 },
  { id: '10-troubleshooting', title: 'Solução de problemas', order: 10 },
]

const CONSTRUCTION_NOTICE = `Conteúdo em construção (MVP 18 Fase 18.3). Esta versão (18.1) é o esqueleto
da área de ajuda — rotas, layout, navegação e guards RBAC. O texto real de cada
capítulo chega na próxima onda após review do stakeholder.`

export function HelpPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialSection = searchParams.get('section') || STUB_TOC[0].id

  const [toc, setToc] = useState<TocChapter[]>(STUB_TOC)
  const [activeId, setActiveId] = useState<string>(initialSection)
  const [section, setSection] = useState<HelpSection | null>(null)
  const [sectionLoading, setSectionLoading] = useState(false)
  const [sectionError, setSectionError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  // Fetch TOC a partir do backend se disponível (18.2); cai pra STUB se falhar.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await apiClient.get<{ chapters: TocChapter[] }>('/help/toc')
        if (!cancelled && Array.isArray(res.data?.chapters) && res.data.chapters.length > 0) {
          setToc(res.data.chapters)
        }
      } catch {
        // silencioso: em 18.1 o endpoint ainda não existe; o stub cobre.
      }
    })()
    return () => { cancelled = true }
  }, [])

  // Fetch conteúdo da seção ativa.
  useEffect(() => {
    let cancelled = false
    setSectionLoading(true)
    setSectionError(null)
    ;(async () => {
      try {
        const res = await apiClient.get<HelpSection>(`/help/section/${activeId}`)
        if (!cancelled) {
          setSection(res.data)
        }
      } catch (err: unknown) {
        if (!cancelled) {
          // Em 18.1 (endpoint ausente) ou 18.2 (seção ainda sem conteúdo real),
          // exibe o placeholder. O chapter title vem do TOC que já temos.
          const chapter = toc.find((c) => c.id === activeId)
          setSection({
            id: activeId,
            title: chapter?.title || activeId,
            markdown: CONSTRUCTION_NOTICE,
          })
          // Não seta error — o placeholder é comportamento esperado nesta onda.
          void getErrorMessage(err)
        }
      } finally {
        if (!cancelled) setSectionLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [activeId, toc])

  const filteredToc = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return toc
    return toc.filter((c) => c.title.toLowerCase().includes(q))
  }, [toc, search])

  const handleSelect = (id: string) => {
    setActiveId(id)
    setSearchParams({ section: id })
  }

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center gap-3 px-6 py-4 border-b border-slate-800 bg-slate-900/40">
        <HelpCircle className="w-6 h-6 text-violet-400" />
        <div>
          <h1 className="text-slate-100 text-lg font-semibold">Ajuda</h1>
          <p className="text-slate-500 text-xs">Documentação operacional do GCA — Admin + GP</p>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* TOC lateral */}
        <aside className="w-72 flex-shrink-0 border-r border-slate-800 bg-slate-900/20 overflow-y-auto">
          <div className="p-3 border-b border-slate-800">
            <label htmlFor="help-search" className="sr-only">Buscar no help</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                id="help-search"
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar capítulo..."
                className="w-full pl-9 pr-3 py-2 bg-slate-800/60 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-violet-500"
              />
            </div>
            <p className="text-slate-600 text-[10px] mt-2">
              Busca full-text chega na Fase 18.4; por ora filtra só títulos.
            </p>
          </div>
          <nav aria-label="Capítulos do help" className="p-2 space-y-0.5">
            {filteredToc.map((chapter) => (
              <button
                key={chapter.id}
                onClick={() => handleSelect(chapter.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                  activeId === chapter.id
                    ? 'bg-violet-500/15 text-violet-200 border border-violet-500/30'
                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }`}
              >
                <BookOpen className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="flex-1">{chapter.title}</span>
                {activeId === chapter.id && <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            ))}
            {filteredToc.length === 0 && (
              <p className="text-slate-600 text-xs px-3 py-4 text-center italic">
                Nenhum capítulo contém "{search}"
              </p>
            )}
          </nav>
        </aside>

        {/* Conteúdo central */}
        <main className="flex-1 overflow-y-auto px-8 py-6" role="main" aria-live="polite">
          {sectionLoading && (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="w-6 h-6 text-violet-400 animate-spin" />
            </div>
          )}

          {!sectionLoading && sectionError && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
              <p className="text-red-300 text-sm">{sectionError}</p>
            </div>
          )}

          {!sectionLoading && !sectionError && section && (
            <article className="prose prose-invert max-w-none">
              <h1 className="text-slate-100 text-2xl font-semibold mb-4">{section.title}</h1>
              {/* MVP 18 Fase 18.5 troca este <pre> por renderer markdown de verdade.
                  Por ora mostra o markdown cru num <pre> pra texto ficar legível
                  sem dependência nova. */}
              <pre className="whitespace-pre-wrap text-slate-300 text-sm leading-relaxed font-sans bg-transparent border-0 p-0">
                {section.markdown}
              </pre>
            </article>
          )}
        </main>
      </div>
    </div>
  )
}
