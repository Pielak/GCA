import { useState, useEffect, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import { Search, BookOpen, ChevronRight, Loader2, HelpCircle, X } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { getErrorMessage } from '@/lib/errors'

// MVP 18 Fases 18.1 → 18.5:
// - 18.1/18.2: rotas + skeleton + endpoints backend.
// - 18.3: conteúdo real dos 10 capítulos.
// - 18.4: busca FTS5 no backend.
// - 18.5: renderer markdown (react-markdown + remark-gfm + rehype-highlight),
//   integração busca + navegação, testes e2e mínimos.

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

interface SearchHit {
  section_id: string
  title: string
  snippet: string
  rank: number
}

interface SearchResponse {
  backend: string
  query: string
  limit: number
  results: SearchHit[]
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

export function HelpPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialSection = searchParams.get('section') || STUB_TOC[0].id

  const [toc, setToc] = useState<TocChapter[]>(STUB_TOC)
  const [activeId, setActiveId] = useState<string>(initialSection)
  const [section, setSection] = useState<HelpSection | null>(null)
  const [sectionLoading, setSectionLoading] = useState(false)
  const [sectionError, setSectionError] = useState<string | null>(null)

  const [searchInput, setSearchInput] = useState('')
  const [searchResults, setSearchResults] = useState<SearchHit[]>([])
  const [searching, setSearching] = useState(false)

  // Fetch TOC do backend.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await apiClient.get<{ chapters: TocChapter[] }>('/help/toc')
        if (!cancelled && Array.isArray(res.data?.chapters) && res.data.chapters.length > 0) {
          setToc(res.data.chapters)
        }
      } catch {
        // silencioso: stub local cobre durante dev sem backend.
      }
    })()
    return () => { cancelled = true }
  }, [])

  // Fetch seção ativa.
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
          setSectionError(getErrorMessage(err))
          setSection(null)
        }
      } finally {
        if (!cancelled) setSectionLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [activeId])

  // Debounced search: 300ms após o último keystroke.
  useEffect(() => {
    const q = searchInput.trim()
    if (!q) {
      setSearchResults([])
      return
    }
    const handle = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await apiClient.get<SearchResponse>(
          `/help/search?q=${encodeURIComponent(q)}&limit=20`
        )
        setSearchResults(res.data?.results || [])
      } catch {
        setSearchResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(handle)
  }, [searchInput])

  const handleSelect = useCallback((id: string) => {
    setActiveId(id)
    setSearchParams({ section: id })
  }, [setSearchParams])

  const handleSelectFromSearch = useCallback((hit: SearchHit) => {
    handleSelect(hit.section_id)
    // Mantém o input para o user ver o que buscou; opcional limpar.
  }, [handleSelect])

  const clearSearch = useCallback(() => {
    setSearchInput('')
    setSearchResults([])
  }, [])

  const filteredToc = useMemo(() => toc, [toc])
  const showingSearchResults = searchInput.trim().length > 0

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
        {/* TOC lateral + busca */}
        <aside className="w-72 flex-shrink-0 border-r border-slate-800 bg-slate-900/20 overflow-y-auto">
          <div className="p-3 border-b border-slate-800">
            <label htmlFor="help-search" className="sr-only">Buscar no help</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                id="help-search"
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Buscar em todo o help..."
                className="w-full pl-9 pr-9 py-2 bg-slate-800/60 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-violet-500"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={clearSearch}
                  aria-label="Limpar busca"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {searching && (
              <p className="text-slate-600 text-[10px] mt-2 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Buscando...
              </p>
            )}
          </div>

          {showingSearchResults ? (
            <div className="p-2">
              <p className="px-2 py-1 text-slate-500 text-[10px] uppercase tracking-wider">
                Resultados ({searchResults.length})
              </p>
              {searchResults.length === 0 && !searching && (
                <p className="text-slate-600 text-xs px-3 py-4 text-center italic">
                  Nenhum capítulo contém "{searchInput}"
                </p>
              )}
              {searchResults.map((hit) => (
                <button
                  key={hit.section_id}
                  onClick={() => handleSelectFromSearch(hit)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    activeId === hit.section_id
                      ? 'bg-violet-500/15 text-violet-200 border border-violet-500/30'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  <p className="font-medium text-slate-200 truncate">{hit.title}</p>
                  <p
                    className="text-[11px] text-slate-500 mt-1 line-clamp-2 [&_mark]:bg-amber-400/30 [&_mark]:text-amber-200 [&_mark]:px-0.5 [&_mark]:rounded"
                    dangerouslySetInnerHTML={{ __html: hit.snippet }}
                  />
                </button>
              ))}
            </div>
          ) : (
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
            </nav>
          )}
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
              <p className="text-red-300 text-sm">Erro ao carregar seção: {sectionError}</p>
            </div>
          )}

          {!sectionLoading && !sectionError && section && (
            <article className="help-article max-w-4xl">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {section.markdown}
              </ReactMarkdown>
            </article>
          )}
        </main>
      </div>
    </div>
  )
}
