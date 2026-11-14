import { useCallback, useEffect, useState } from 'react'
import { copy, type Language } from './i18n'

type Profile = 'easy' | 'random' | 'aggressive'
type PokerEvent = {
  kind: string
  action?: { seat: number; kind: string; amount: number | null; all_in?: boolean }
  seat?: number
  cards?: string[]
}
type Game = {
  id: string
  hand_number: number
  players: number
  active_seats: number[]
  bot_profiles: Profile[]
  button: number
  small_blind: number
  big_blind: number
  finished: boolean
  session_over: boolean
  hole_cards: string[]
  board: string[]
  stacks: number[]
  pot: number
  street: string
  to_call?: number
  min_raise?: number
  max_raise?: number
  raise_presets?: Record<string, number>
  legal_actions: string[]
  events: PokerEvent[]
  payouts?: number[]
  split_pot?: boolean
}
const suits: Record<string, string> = { s: '♠', h: '♥', d: '♦', c: '♣' }
function Card({ value, index = 0 }: { value?: string; index?: number }) {
  return (
    <span className={`playing-card ${value ? 'face' : 'back'} ${value && /[hd]/.test(value) ? 'red' : ''}`}
      style={{ animationDelay: `${index * 65}ms` }} aria-label={value ?? '••'}>
      {value ? <><b>{value.slice(0, -1)}</b><span>{suits[value.slice(-1)]}</span></> : '♠'}
    </span>
  )
}
function initialLanguage(): Language {
  try { return localStorage.getItem('poker-language') === 'en' ? 'en' : 'fr' }
  catch { return 'fr' }
}
export default function App() {
  const [language, setLanguage] = useState<Language>(initialLanguage)
  const t = copy[language]
  const [game, setGame] = useState<Game | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [amount, setAmount] = useState(4)
  const [players, setPlayers] = useState(3)
  const [stack, setStack] = useState(100)
  const [bigBlind, setBigBlind] = useState(2)
  const [profiles, setProfiles] = useState<Profile[]>(['easy', 'random', 'easy', 'random', 'easy', 'random', 'easy', 'random'])
  const [settingsOpen, setSettingsOpen] = useState(true)
  const [autoNext, setAutoNext] = useState(true)
  const [countdown, setCountdown] = useState(5)

  useEffect(() => {
    document.documentElement.lang = language
    try { localStorage.setItem('poker-language', language) } catch { /* Storage can be disabled. */ }
  }, [language])

  const send = useCallback(async (operation: 'start' | 'next' | 'act', action?: string) => {
    setBusy(true)
    setError('')
    const url = operation === 'start' ? '/api/play' : `/api/play/${game?.id}/${operation}`
    const body = operation === 'start'
      ? { players, starting_stack: stack, big_blind: bigBlind, bots: profiles.slice(0, players - 1) }
      : operation === 'act'
        ? { type: action, ...(['bet', 'raise'].includes(action ?? '') ? { amount } : {}) }
        : undefined
    try {
      const response = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        ...(body ? { body: JSON.stringify(body) } : {}),
      })
      const data = await response.json()
      if (!response.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'invalid')
        return
      }
      setGame(data)
      setCountdown(5)
      setAmount(data.min_raise ?? 4)
      setSettingsOpen(false)
    } catch { setError('connection') }
    finally { setBusy(false) }
  }, [game?.id, players, stack, bigBlind, profiles, amount])

  useEffect(() => {
    if (!autoNext || !game?.finished || game.session_over || busy || error || settingsOpen) return
    const interval = window.setInterval(() => setCountdown(value => Math.max(0, value - 1)), 1000)
    const timeout = window.setTimeout(() => {
      if (document.visibilityState !== 'hidden') void send('next')
      else setAutoNext(false)
    }, 5000)
    return () => { window.clearInterval(interval); window.clearTimeout(timeout) }
  }, [autoNext, game?.finished, game?.session_over, game?.hand_number, busy, error, settingsOpen, send])

  function name(seat: number) { return seat === 0 ? t.you : `${t.bot} ${seat}` }
  const profileNames = { easy: t.easy, random: t.random, aggressive: t.aggressive }
  const streets: Record<string, string> = { preflop: t.preflop, flop: t.flop, turn: t.turnStreet, river: t.river, showdown: t.showdown }
  const verbs: Record<string, string> = { fold: t.folds, check: t.checks, call: t.calls, bet: t.bets, raise: t.raises, small_blind: t.smallBlind, big_blind: t.bigBlind, ante: t.ante }
  const labels: Record<string, string> = { fold: t.fold, check: t.check, call: `${t.call} · ${game?.to_call ?? 0}`, bet: t.bet, raise: t.raise }
  const errors: Record<string, string> = { connection: t.connection, invalid: t.invalid, invalid_amount: t.invalid, unexpected_amount: t.invalid, table_expired: t.expired, hand_finished: t.finished, hand_in_progress: t.inProgress, session_over: t.finished, illegal_action: t.unavailable }
  const sized = game?.legal_actions.some(action => action === 'bet' || action === 'raise')
  const validAmount = Number.isInteger(amount) && amount >= (game?.min_raise ?? 0) && amount <= (game?.max_raise ?? 0)
  const net = game?.payouts?.[0] ?? 0
  const resultKind = game?.split_pot ? 'split' : net > 0 ? 'win' : net < 0 ? 'loss' : 'unchanged'
  const resultTitle = game?.session_over ? ((game.stacks[0] ?? 0) > 0 ? t.champion : t.busted) : t[resultKind]
  const activePlayers = game?.players ?? players
  const activeProfiles = game?.bot_profiles ?? profiles
  const presetLabels: Record<string, string> = { third: `⅓ ${t.pot}`, half: `½ ${t.pot}`, two_thirds: `⅔ ${t.pot}`, pot: t.pot, one_half: `1.5× ${t.pot}` }

  return (
    <main className="arena">
      <header>
        <div><p className="eyebrow">{t.subtitle}</p><h1>Poker Bot Arena</h1></div>
        <div className="header-actions">
          <label className="language-picker">{t.language}<select value={language} onChange={e => setLanguage(e.target.value as Language)}><option value="fr">Français</option><option value="en">English</option></select></label>
          <button className="secondary" onClick={() => { setCountdown(5); setSettingsOpen(open => !open) }}>{t.settings}</button>
        </div>
      </header>

      {settingsOpen && <form className="settings" onSubmit={e => { e.preventDefault(); void send('start') }}>
        <div className="setting-fields">
          <label>{t.players}<select value={players} disabled={busy} onChange={e => setPlayers(Number(e.target.value))}>{Array.from({ length: 8 }, (_, i) => <option key={i + 2} value={i + 2}>{i + 2}</option>)}</select></label>
          <label>{t.stack}<input type="number" min={20} max={100000} step={1} required value={stack} disabled={busy} onChange={e => setStack(Number(e.target.value))} /></label>
          <label>{t.blinds}<select value={bigBlind} disabled={busy} onChange={e => setBigBlind(Number(e.target.value))}>{[2, 4, 10, 20, 50, 100].map(value => <option key={value} value={value}>{value / 2} / {value}</option>)}</select></label>
        </div>
        <fieldset><legend>{t.profiles}</legend><div className="profile-grid">{profiles.slice(0, players - 1).map((profile, i) => <label key={i}>{t.bot} {i + 1}<select value={profile} disabled={busy} onChange={e => setProfiles(current => current.map((v, index) => index === i ? e.target.value as Profile : v))}>{(['easy', 'random', 'aggressive'] as Profile[]).map(value => <option key={value} value={value}>{profileNames[value]}</option>)}</select></label>)}</div></fieldset>
        <p className="hint">{t.profileHint} {game ? t.resetHint : ''}</p>
        <button className="primary" disabled={busy || !Number.isInteger(stack) || stack < 20 || bigBlind > stack}>{game ? t.restart : t.start}</button>
      </form>}

      <div className="layout"><section className="play-area" aria-label="Poker">
        <div className="table-toolbar"><span className="badge">{t.blinds} {game?.small_blind ?? bigBlind / 2} / {game?.big_blind ?? bigBlind} · {activePlayers} {t.playerUnit}</span><strong>{t.hand} #{game?.hand_number ?? 1}</strong><span>{t.total} · {game?.stacks.reduce((a, b) => a + b, 0) ?? players * stack}{game && !game.finished ? ` + ${game.pot}` : ''}</span></div>
        <div className={`felt ${game?.finished ? `result-${resultKind}` : ''}`}>
          <div className="bot-grid" style={{ gridTemplateColumns: `repeat(${Math.min(4, activePlayers - 1)}, minmax(0, 1fr))` }}>
            {Array.from({ length: activePlayers - 1 }, (_, i) => i + 1).map(seat => {
              const shown = game?.events.find(event => event.kind === 'showdown_revealed' && event.seat === seat)?.cards
              const folded = game?.events.some(event => event.action?.seat === seat && event.action.kind === 'fold')
              const won = game?.finished && (game.payouts?.[seat] ?? 0) > 0
              return <div className={`seat bot ${folded ? 'is-folded' : ''} ${won ? 'is-winner' : ''}`} key={seat}>
                <p>{name(seat)} {game?.button === seat && <span className="dealer" title={t.dealer}>D</span>}</p>
                <small className="profile-name">{profileNames[activeProfiles[seat - 1] ?? 'random']}</small>
                <strong>{game?.stacks[seat] ?? stack} <small>{t.chips}</small></strong>
                <div className="cards">{[0, 1].map(index => <Card key={`${game?.hand_number}-${shown?.[index] ?? 'back'}-${index}`} value={shown?.[index]} index={index} />)}</div>
                <span className="seat-status">{(game?.stacks[seat] ?? stack) === 0 ? (!game?.finished && game?.active_seats.includes(seat) ? t.allIn : t.eliminated) : folded ? t.folded : won ? `+${game?.payouts?.[seat]}` : ''}</span>
              </div>
            })}
          </div>
          <div className="community"><p className="eyebrow">{game ? streets[game.street] : t.ready}</p><h2>{game?.finished ? t.settled : `${t.pot} · ${game?.pot ?? 0}`}</h2><div className="cards board">{Array.from({ length: 5 }, (_, i) => <Card key={`${game?.hand_number}-${game?.board[i] ?? 'back'}-${i}`} value={game?.board[i]} index={i} />)}</div></div>
          <div className={`seat human ${game?.finished && net > 0 ? 'is-winner' : ''}`}><div className="cards">{[0, 1].map(index => <Card key={`${game?.hand_number}-${game?.hole_cards[index] ?? 'back'}-${index}`} value={game?.hole_cards[index]} index={index} />)}</div><p>{t.you} {(!game || game.button === 0) && <span className="dealer" title={t.dealer}>D</span>}</p><strong>{game?.stacks[0] ?? stack} <small>{t.chips}</small></strong></div>
        </div>

        <section className="controls" aria-label={t.turn}>
          <div className="control-title"><p role="status">{busy ? t.thinking : game?.finished ? resultTitle : game ? t.turn : t.ready}</p><label className="auto-toggle"><input type="checkbox" checked={autoNext} onChange={e => { setCountdown(5); setAutoNext(e.target.checked) }} />{t.continuous}</label></div>
          {game?.finished && <div className={`result-banner ${resultKind}`} key={`${game.id}-${game.hand_number}`}><span className="result-icon" aria-hidden="true">{resultKind === 'win' ? '✦' : resultKind === 'split' ? '⇄' : '•'}</span><div><strong>{resultTitle}</strong><p>{t.net} : {net > 0 ? '+' : ''}{net} {t.chips}</p></div></div>}
          {error && <p className="error" role="alert">{errors[error] ?? t.invalid}</p>}
          {sized && !game?.finished && <div className="sizing">
            <div className="amount-row"><label>{t.amount}<input aria-label={t.amount} type="number" min={game?.min_raise} max={game?.max_raise} step={1} value={amount} onChange={e => setAmount(Number(e.target.value))} disabled={busy} /></label><span>{game?.min_raise}–{game?.max_raise} {t.chips}</span></div>
            <input className="bet-slider" aria-label={`${t.amount} slider`} type="range" min={game?.min_raise} max={game?.max_raise} value={Number.isFinite(amount) ? amount : game?.min_raise} onChange={e => setAmount(Number(e.target.value))} disabled={busy} />
            <div className="presets"><button disabled={busy} onClick={() => setAmount(game?.min_raise ?? 0)}>{t.minimum}<small>{game?.min_raise}</small></button>{Object.entries(game?.raise_presets ?? {}).map(([key, value]) => <button key={key} disabled={busy} className={amount === value ? 'selected' : ''} onClick={() => setAmount(value)}>{presetLabels[key]}<small>{value}</small></button>)}<button disabled={busy} onClick={() => setAmount(game?.max_raise ?? 0)}>{t.allIn}<small>{game?.max_raise}</small></button></div>
          </div>}
          <div className="buttons">{game && !game.finished ? game.legal_actions.map(action => <button className={action === 'fold' ? 'secondary' : 'primary'} key={action} disabled={busy || (['bet', 'raise'].includes(action) && !validAmount)} onClick={() => void send('act', action)}>{labels[action]}{['bet', 'raise'].includes(action) ? ` · ${Number.isFinite(amount) ? amount : '—'}` : ''}</button>) : game?.finished ? <button className="primary" disabled={busy} onClick={() => void send(game.session_over ? 'start' : 'next')}>{game.session_over ? t.restart : t.next}</button> : !settingsOpen && <button className="primary" disabled={busy} onClick={() => setSettingsOpen(true)}>{t.start}</button>}</div>
          {game?.finished && !game.session_over && autoNext && !settingsOpen && !error && <p className="countdown">{t.nextIn} {countdown} {t.seconds}…</p>}
          <p className="hint">{t.continuity} {t.privacy}</p>
        </section>
      </section><aside><p className="eyebrow">{t.hand} #{game?.hand_number ?? 1}</p><h2>{t.log}</h2><ol aria-label={t.log}>{game?.events.filter(event => event.kind === 'player_acted').map((event, i) => <li key={i}><strong>{name(event.action?.seat ?? 0)}</strong><span>{verbs[event.action?.kind ?? ''] ?? event.action?.kind} {event.action?.amount ?? ''}{event.action?.all_in ? ` · ${t.allIn}` : ''}</span></li>)}</ol>{!game && <p className="hint">{t.noLog}</p>}</aside></div>
    </main>
  )
}
