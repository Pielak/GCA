import React from 'react'

export function AnimatedGearsBackground() {
  return (
    <div className="absolute inset-0 w-full h-full overflow-hidden">
      {/* Fundo com imagem real de engrenagens (estática) */}
      <div
        className="absolute inset-0 w-full h-full"
        style={{
          backgroundImage: 'url(/images/gears-3d-bg.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          opacity: 0.7,
        }}
      />

      {/* Overlay gradiente para legibilidade */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#0f0f1e]/95 via-[#0f0f1e]/75 to-[#0f0f1e]/40 pointer-events-none" />

      {/* Glow sutil ciano */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at 25% 50%, rgba(0,184,204,0.1) 0%, transparent 70%)',
        }}
      />
    </div>
  )
}
