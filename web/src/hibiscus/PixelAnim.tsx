// Hibiscus pixel components (React only). Assets are served from PIXEL_BASE.
// PIXEL UNIT RULE: every art pixel is drawn at PX_UNIT css px. There is deliberately no `scale`
// prop — pick a sprite drawn at the resolution you need (e.g. <Hibi size="mini" />).
// Optional props accept `undefined` so the components work under `exactOptionalPropertyTypes`.
import type { CSSProperties } from 'react'
import { GLYPHS, type GlyphName } from './glyphs.gen'
import { ANIMS, SPRITES, type AnimName, type SpriteName } from './sprites.gen'

export const PIXEL_BASE = '/pixel'
export const PX_UNIT = 2

/** Static sprite. */
export function Sprite({ name, alt = '', className, style }: {
  name: SpriteName; alt?: string | undefined; className?: string | undefined; style?: CSSProperties | undefined
}) {
  const s = SPRITES[name]
  return (
    <img src={`${PIXEL_BASE}/${name}.png`} width={s.w * PX_UNIT} height={s.h * PX_UNIT} alt={alt}
      aria-hidden={alt ? undefined : true} draggable={false} className={'pixelated' + (className ? ' ' + className : '')}
      style={{ imageRendering: 'pixelated', ...style }} />
  )
}

/** Sprite-strip animation. Wrap in an element with class `px-hover` to play only on hover/focus. */
export function PixelAnim({ name, label, className, style, fps }: {
  name: AnimName; label?: string | undefined; className?: string | undefined; style?: CSSProperties | undefined; fps?: number | undefined
}) {
  const a = ANIMS[name]
  const vars = {
    '--src': `url(${PIXEL_BASE}/anim/${name}.png)`, '--w': a.w, '--h': a.h, '--n': a.frames,
    '--dur': `${a.frames / (fps ?? a.fps)}s`,
  } as CSSProperties
  return (
    <span className={'px-anim' + (className ? ' ' + className : '')} style={{ ...vars, ...style }}
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true} />
  )
}

/** 8x8 UI glyph (16 px), painted with currentColor — use inside buttons, inputs and text. */
export function PxIcon({ name, label, className }: { name: GlyphName; label?: string | undefined; className?: string | undefined }) {
  return (
    <svg viewBox="0 0 8 8" width={8 * PX_UNIT} height={8 * PX_UNIT} fill="currentColor" shapeRendering="crispEdges"
      className={'px-icon' + (className ? ' ' + className : '')} role={label ? 'img' : undefined} aria-label={label}
      aria-hidden={label ? undefined : true}>
      <path d={GLYPHS[name]} />
    </svg>
  )
}

export type HibiMood = 'idle' | 'wave' | 'happy' | 'working' | 'sleep' | 'sad'

/** Hibi, the mascot: a robot arm holding a hibiscus. hero = 48x48 art (96 px), mini = 24x24 art (48 px). */
export function Hibi({ mood = 'idle', size = 'hero', label, className }: {
  mood?: HibiMood; size?: 'hero' | 'mini'; label?: string | undefined; className?: string | undefined
}) {
  const name = (size === 'mini' ? `hibi_mini_${mood}` : `hibi_${mood}`) as AnimName
  return <PixelAnim name={name} label={label} className={className} />
}

/** Grass strip with swaying tufts, mini Hibi and a butterfly — e.g. the bottom of a sidebar. */
export function Garden({ mood = 'idle', tufts = 6, butterfly = true }: { mood?: HibiMood; tufts?: number; butterfly?: boolean }) {
  return (
    <div className="px-garden" aria-hidden="true">
      <div className="px-tufts">{Array.from({ length: tufts }, (_, i) => <PixelAnim key={i} name="grass_tufts" className="px-norim" />)}</div>
      {butterfly && <span className="px-fly-x"><span className="px-fly-y"><PixelAnim name="butterfly" /></span></span>}
      <span className="px-hibi"><Hibi mood={mood} size="mini" /></span>
    </div>
  )
}

/** Hibiscus petals drifting down (absolute, fills the positioned parent). */
export function Petals({ count = 10 }: { count?: number }) {
  return (
    <div className="px-petals" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className="px-fall" style={{
          left: `${(i * 37 + 7) % 100}%`, '--delay': `${-((i * 1.7) % 11)}s`, '--fall': `${9 + (i % 4) * 1.5}s`,
        } as CSSProperties}>
          <span className="px-sway" style={{ animationDelay: `${-(i % 5) * 0.4}s` }}><PixelAnim name="petal" /></span>
        </span>
      ))}
    </div>
  )
}
