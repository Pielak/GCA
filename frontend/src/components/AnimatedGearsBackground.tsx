import React from 'react'

interface GearProps {
  cx: number
  cy: number
  radiusOuter: number
  radiusInner: number
  rotationDuration: number
  rotationDelay: number
  reverse?: boolean
}

function Gear({
  cx,
  cy,
  radiusOuter,
  radiusInner,
  rotationDuration,
  rotationDelay,
  reverse = false,
}: GearProps) {
  // Criar dentes da engrenagem com pequenos arcos
  const teethCount = 12
  const toothLength = (radiusOuter - radiusInner) * 0.5
  const teethElements = []

  for (let i = 0; i < teethCount; i++) {
    const angle = (i / teethCount) * Math.PI * 2 - Math.PI / 2
    const x1 = cx + radiusInner * Math.cos(angle)
    const y1 = cy + radiusInner * Math.sin(angle)
    const x2 = cx + (radiusInner + toothLength) * Math.cos(angle)
    const y2 = cy + (radiusInner + toothLength) * Math.sin(angle)

    teethElements.push(
      <line
        key={`tooth-${i}`}
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.6"
      />
    )
  }

  const animationStyle = {
    animation: `rotate-${reverse ? 'reverse' : 'forward'} ${rotationDuration}s linear infinite`,
    animationDelay: `${rotationDelay}s`,
  } as React.CSSProperties

  return (
    <g style={animationStyle} transformOrigin={`${cx} ${cy}`}>
      {/* Círculo externo */}
      <circle
        cx={cx}
        cy={cy}
        r={radiusOuter}
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        opacity="0.8"
      />

      {/* Dentes */}
      {teethElements}

      {/* Círculo interno (furo) */}
      <circle
        cx={cx}
        cy={cy}
        r={radiusInner * 0.6}
        fill="currentColor"
        opacity="0.5"
      />
    </g>
  )
}

export function AnimatedGearsBackground() {
  // Posições e tamanhos das 12 engrenagens (4 grandes + 8 pequenas)
  // Simulando loop: grande → pequena → grande
  const gears: GearProps[] = [
    // Grandes (radius ~50)
    { cx: 180, cy: 200, radiusOuter: 50, radiusInner: 25, rotationDuration: 12, rotationDelay: 0 },
    { cx: 200, cy: 400, radiusOuter: 50, radiusInner: 25, rotationDuration: 12, rotationDelay: 0.3, reverse: true },

    // Pequenas conectando (radius ~35)
    { cx: 300, cy: 280, radiusOuter: 35, radiusInner: 18, rotationDuration: 9, rotationDelay: 0.6 },
    { cx: 80, cy: 320, radiusOuter: 35, radiusInner: 18, rotationDuration: 9, rotationDelay: 0.9, reverse: true },

    // Micro engrenagens (radius ~28-32)
    { cx: 400, cy: 200, radiusOuter: 28, radiusInner: 14, rotationDuration: 8, rotationDelay: 1.2 },
    { cx: 380, cy: 350, radiusOuter: 28, radiusInner: 14, rotationDuration: 8, rotationDelay: 1.5, reverse: true },
    { cx: 100, cy: 450, radiusOuter: 28, radiusInner: 14, rotationDuration: 8, rotationDelay: 1.8 },
    { cx: 50, cy: 200, radiusOuter: 28, radiusInner: 14, rotationDuration: 8, rotationDelay: 2.1, reverse: true },
    { cx: 280, cy: 120, radiusOuter: 32, radiusInner: 16, rotationDuration: 10, rotationDelay: 2.4 },
    { cx: 320, cy: 450, radiusOuter: 32, radiusInner: 16, rotationDuration: 10, rotationDelay: 2.7, reverse: true },
    { cx: 20, cy: 300, radiusOuter: 30, radiusInner: 15, rotationDuration: 9.5, rotationDelay: 3.0 },
    { cx: 450, cy: 380, radiusOuter: 30, radiusInner: 15, rotationDuration: 9.5, rotationDelay: 3.3, reverse: true },
  ]

  return (
    <>
      <svg
        viewBox="0 0 500 600"
        className="absolute inset-0 w-full h-full pointer-events-none"
        preserveAspectRatio="xMidYMid slice"
      >
        {/* Fundo cinza escuro */}
        <rect width="500" height="600" fill="#0f0f1e" />

        {/* Engrenagens em cor metal escovado */}
        <g className="text-gray-500/60 dark:text-gray-400/70">
          {gears.map((gear, idx) => (
            <Gear key={idx} {...gear} />
          ))}
        </g>
      </svg>

      {/* CSS Keyframes para rotação */}
      <style>{`
        @keyframes rotate-forward {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }

        @keyframes rotate-reverse {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(-360deg);
          }
        }
      `}</style>
    </>
  )
}
