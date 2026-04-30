/**
 * Utilitários para exportar Pilares Vivos em múltiplos formatos
 * Suporta: Markdown, PDF (via HTML/print)
 */

import { PilaresVivosData } from '@/hooks/usePilaresVivos'

const PERSONAS_INFO: Record<string, { label: string; emoji: string }> = {
  P4_Arquiteto: { label: 'Arquiteto', emoji: '🏗️' },
  P1_DBA: { label: 'DBA', emoji: '💾' },
  P2_Compliance: { label: 'Compliance', emoji: '⚖️' },
  P3_Seguranca: { label: 'Segurança', emoji: '🔒' },
  P5_Dev: { label: 'Desenvolvimento', emoji: '💻' },
  P6_Tester: { label: 'Tester', emoji: '🧪' },
  P7_QA: { label: 'QA', emoji: '✓' },
}

const PERSONAS_ORDER = [
  'P4_Arquiteto',
  'P1_DBA',
  'P2_Compliance',
  'P3_Seguranca',
  'P5_Dev',
  'P6_Tester',
  'P7_QA',
]

export function gerarMarkdown(data: PilaresVivosData, nomeProto: string): string {
  const linhas: string[] = []

  // Cabeçalho
  linhas.push(`# Pilares Vivos — ${nomeProto}`)
  linhas.push('')
  linhas.push(
    `**Análise Consolidada das 7 Personas** | Gerado em ${new Date(data.gerado_em || Date.now()).toLocaleString('pt-BR')}`
  )
  linhas.push('')

  // Índice
  linhas.push('## Índice')
  linhas.push('')
  PERSONAS_ORDER.forEach((persona) => {
    const info = PERSONAS_INFO[persona]
    if (info) {
      linhas.push(`- [${info.emoji} ${info.label}](#${persona.toLowerCase()})`)
    }
  })
  linhas.push('')

  // Estatísticas
  linhas.push('## Resumo Executivo')
  linhas.push('')
  const completasCount = PERSONAS_ORDER.filter(
    (p) => data.documento[p]?.status === 'completo'
  ).length
  const comErroCount = PERSONAS_ORDER.filter((p) => data.documento[p]?.status === 'erro')
    .length
  linhas.push(`- **Análises Completas**: ${completasCount}/${PERSONAS_ORDER.length}`)
  linhas.push(`- **Erros Detectados**: ${comErroCount}`)
  linhas.push(
    `- **Atualizado em**: ${new Date(data.regenerado_em || data.gerado_em || Date.now()).toLocaleString('pt-BR')}`
  )
  linhas.push('')

  // Seções por persona
  PERSONAS_ORDER.forEach((persona) => {
    const parecer = data.documento[persona]
    const info = PERSONAS_INFO[persona]

    if (!info || !parecer) return

    linhas.push(`## ${persona.toLowerCase()}`)
    linhas.push(`### ${info.emoji} ${info.label}`)
    linhas.push('')

    // Status
    const status =
      parecer.status === 'completo'
        ? '✅ Completo'
        : parecer.status === 'erro'
          ? '❌ Erro'
          : '⏳ Processando'
    linhas.push(`**Status**: ${status}`)
    linhas.push('')

    // Parecer
    if (parecer.parecer) {
      if (typeof parecer.parecer === 'object') {
        linhas.push('**Parecer Estruturado**:')
        linhas.push('```json')
        linhas.push(JSON.stringify(parecer.parecer, null, 2))
        linhas.push('```')
      } else {
        linhas.push(`**Parecer**: ${parecer.parecer}`)
      }
      linhas.push('')
    }

    // Análise de texto
    if (parecer.analise_texto) {
      linhas.push('**Análise**:')
      linhas.push(parecer.analise_texto)
      linhas.push('')
    }

    // Discovery Tasks
    if (parecer.dts && parecer.dts.length > 0) {
      linhas.push(`### Discovery Tasks (${parecer.dts.length})`)
      linhas.push('')
      parecer.dts.forEach((dt: any, idx: number) => {
        const dtData = typeof dt === 'string' ? { descricao: dt } : dt
        linhas.push(`#### ${dtData.id || dtData.titulo || `Task ${idx + 1}`}`)
        linhas.push('')
        if (dtData.impacto) {
          linhas.push(`- **Impacto**: ${dtData.impacto}`)
        }
        if (dtData.descricao) {
          linhas.push(`- **Descrição**: ${dtData.descricao}`)
        }
        if (dtData.recomendacao) {
          linhas.push(`- **Recomendação**: ${dtData.recomendacao}`)
        }
        linhas.push('')
      })
    }

    linhas.push('---')
    linhas.push('')
  })

  // Rodapé
  linhas.push('## Informações do Documento')
  linhas.push('')
  linhas.push(`- **Gerado por**: ${data.gerado_por}`)
  linhas.push(`- **Data**: ${new Date(data.gerado_em || Date.now()).toLocaleString('pt-BR')}`)
  if (data.regenerado_em) {
    linhas.push(`- **Última Regeneração**: ${new Date(data.regenerado_em).toLocaleString('pt-BR')}`)
  }
  linhas.push('')

  return linhas.join('\n')
}

export function exportarMarkdown(data: PilaresVivosData, nomeProto: string) {
  const markdown = gerarMarkdown(data, nomeProto)
  const blob = new Blob([markdown], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Pilares-Vivos-${nomeProto}-${new Date().toISOString().split('T')[0]}.md`
  a.click()
  URL.revokeObjectURL(url)
}

export function exportarPDF(data: PilaresVivosData, nomeProto: string) {
  const markdown = gerarMarkdown(data, nomeProto)
  const html = markdownToHTML(markdown)

  const janela = window.open('', '_blank')
  if (janela) {
    janela.document.write(`
      <!DOCTYPE html>
      <html lang="pt-BR">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Pilares Vivos — ${nomeProto}</title>
        <style>
          body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: white;
          }
          h1 { color: #059669; border-bottom: 2px solid #059669; padding-bottom: 10px; }
          h2 { color: #047857; margin-top: 30px; }
          h3 { color: #059669; }
          h4 { color: #10b981; }
          ul { margin: 10px 0; }
          li { margin: 5px 0; }
          pre { background: #f3f4f6; padding: 10px; border-radius: 4px; overflow-x: auto; }
          code { background: #f3f4f6; padding: 2px 6px; border-radius: 3px; }
          .status { font-weight: bold; }
          hr { border: none; border-top: 2px solid #e5e7eb; margin: 20px 0; }
          @media print {
            body { background: white; }
            a { color: #059669; }
          }
        </style>
      </head>
      <body>
        ${html}
        <script>
          window.print();
        </script>
      </body>
      </html>
    `)
    janela.document.close()
  }
}

function markdownToHTML(markdown: string): string {
  let html = markdown

  // Títulos
  html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>')

  // Negrito
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

  // Itálico
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>')

  // Linhas horizontais
  html = html.replace(/^---$/gm, '<hr>')

  // Listas
  html = html.replace(/^\- (.*?)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')

  // Código (blocos)
  html = html.replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>')

  // Quebras de linha
  html = html.replace(/\n\n/g, '</p><p>')
  html = `<p>${html}</p>`

  // Limpar paragrafos vazios
  html = html.replace(/<p><\/p>/g, '')

  return html
}

export function copiarParaClipboard(data: PilaresVivosData, nomeProto: string) {
  const markdown = gerarMarkdown(data, nomeProto)
  navigator.clipboard.writeText(markdown).then(
    () => {
      console.log('Pilares Vivos copiado para clipboard')
    },
    (err) => {
      console.error('Erro ao copiar:', err)
    }
  )
}
