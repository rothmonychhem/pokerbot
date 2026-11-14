import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

import App from './App'

afterEach(() => vi.unstubAllGlobals())

describe('App', () => {
  it('renders the product title', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /poker bot arena/i })).toBeInTheDocument()
  })

  it('starts a hand, sends a legal action, and offers another hand after settlement', async () => {
    const first = { id: 'test', finished: false, hole_cards: ['As', 'Kd'], board: [], stacks: [100, 99, 98], pot: 3, street: 'preflop', to_call: 2, min_raise: 4, max_raise: 100, legal_actions: ['fold', 'call', 'raise'], events: [] }
    const ended = { ...first, finished: true, legal_actions: [], payouts: [-2, 2, 0], stacks: [98, 102, 100] }
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => first }).mockResolvedValueOnce({ ok: true, json: async () => ended })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Jouer contre les bots' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Suivre · 2' }))
    expect(await screen.findByRole('button', { name: 'Nouvelle main' })).toBeInTheDocument()
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/play/test/act')
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1].body)).toEqual({ type: 'call' })
    expect(screen.getByText('Tu perds 2 jetons.')).toBeInTheDocument()
  })

  it('shows connection errors and lets the player retry', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Connexion impossible.')))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Jouer contre les bots' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Connexion impossible.')
    expect(screen.getByRole('button', { name: 'Jouer contre les bots' })).toBeEnabled()
  })
})
