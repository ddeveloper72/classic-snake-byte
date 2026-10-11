/**
 * Browser adapter for the server-authoritative Snakebite engine.
 *
 * Learning note:
 * Canvas is used instead of a game framework because Snakebite needs only a
 * small grid renderer. The backend remains authoritative: the browser sends
 * player intentions, then renders only state broadcast by the server.
 */
import './style.css'

type Direction = 'up' | 'right' | 'down' | 'left'
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface GameState {
  width: number
  height: number
  snake: [number, number][]
  food: [number, number]
  direction: Direction
  score: number
  level: number
  started: boolean
  paused: boolean
  game_over: boolean
  demo_mode: boolean
}

const CANVAS_WIDTH = 720
const CANVAS_HEIGHT = 480
const DIRECTIONS: readonly Direction[] = ['up', 'right', 'down', 'left']

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <main class="shell">
    <header class="masthead">
      <div>
        <p class="eyebrow">Apple IIe spirit. Modern Python engine.</p>
        <h1>SNAKEBITE</h1>
      </div>
      <div class="score-panel" aria-live="polite">
        <div class="score-box">
          <span>PLAYER</span>
          <strong id="player-name">PLAYER</strong>
        </div>
        <div class="score-box">
          <span>SCORE</span>
          <strong id="score">000000</strong>
        </div>
        <div class="score-box">
          <span>LEVEL</span>
          <strong id="level">1</strong>
        </div>
      </div>
    </header>

    <section class="game-frame" aria-label="Snakebite game">
      <canvas
        id="game"
        width="${CANVAS_WIDTH}"
        height="${CANVAS_HEIGHT}"
        aria-label="Snakebite game board"
      ></canvas>
      <div id="overlay" class="overlay">
        <strong id="overlay-title">CONNECTING</strong>
        <span id="overlay-message">Starting the game link...</span>
      </div>
    </section>

    <section class="controls" aria-label="Game controls">
      <div class="button-row">
        <button id="start" class="primary" type="button">NEW GAME</button>
        <button id="pause" type="button" disabled>PAUSE</button>
      </div>
      <div class="direction-pad" aria-label="Direction controls">
        <button type="button" data-direction="up" aria-label="Move up">▲</button>
        <button type="button" data-direction="left" aria-label="Move left">◀</button>
        <button type="button" data-direction="down" aria-label="Move down">▼</button>
        <button type="button" data-direction="right" aria-label="Move right">▶</button>
      </div>
      <p class="instructions">
        Arrow keys or WASD to steer <span aria-hidden="true">•</span>
        Space to pause
      </p>
      <p id="connection" class="connection" data-status="connecting">
        Connecting to game server
      </p>
    </section>
  </main>
`

const canvas = requireElement<HTMLCanvasElement>('#game')
const context = canvas.getContext('2d')
if (context === null) {
  throw new Error('This browser does not support the Canvas 2D API.')
}

const score = requireElement<HTMLElement>('#score')
const level = requireElement<HTMLElement>('#level')
const playerName = requireElement<HTMLElement>('#player-name')
const overlay = requireElement<HTMLElement>('#overlay')
const overlayTitle = requireElement<HTMLElement>('#overlay-title')
const overlayMessage = requireElement<HTMLElement>('#overlay-message')
const connection = requireElement<HTMLElement>('#connection')
const startButton = requireElement<HTMLButtonElement>('#start')
const pauseButton = requireElement<HTMLButtonElement>('#pause')

let socket: WebSocket | null = null
let state: GameState | null = null
let reconnectTimer: number | null = null

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector)
  if (element === null) {
    throw new Error(`Required page element is missing: ${selector}`)
  }
  return element
}

function websocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/game`
}

function setConnectionStatus(status: ConnectionStatus, message: string): void {
  connection.dataset.status = status
  connection.textContent = message
}

function connect(): void {
  if (
    socket?.readyState === WebSocket.OPEN ||
    socket?.readyState === WebSocket.CONNECTING
  ) {
    return
  }

  setConnectionStatus('connecting', 'Connecting to game server')
  socket = new WebSocket(websocketUrl())

  socket.addEventListener('open', () => {
    setConnectionStatus('connected', 'Game server connected')
  })

  socket.addEventListener('message', (event: MessageEvent<string>) => {
    try {
      const nextState: unknown = JSON.parse(event.data)
      if (!isGameState(nextState)) {
        throw new Error('The game server returned an invalid state.')
      }
      state = nextState
      render(nextState)
    } catch (error) {
      showClientError(error)
    }
  })

  socket.addEventListener('close', () => {
    setConnectionStatus('disconnected', 'Server disconnected — retrying')
    showOverlay('CONNECTION LOST', 'Waiting for the game server...')
    reconnectTimer = window.setTimeout(connect, 1500)
  })

  socket.addEventListener('error', () => {
    setConnectionStatus('disconnected', 'Unable to reach game server')
  })
}

function isGameState(value: unknown): value is GameState {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const candidate = value as Partial<GameState>
  return (
    Number.isInteger(candidate.width) &&
    Number(candidate.width) > 0 &&
    Number.isInteger(candidate.height) &&
    Number(candidate.height) > 0 &&
    Array.isArray(candidate.snake) &&
    candidate.snake.length > 0 &&
    candidate.snake.every(isCoordinate) &&
    isCoordinate(candidate.food) &&
    DIRECTIONS.includes(candidate.direction as Direction) &&
    Number.isInteger(candidate.score) &&
    Number(candidate.score) >= 0 &&
    Number.isInteger(candidate.level) &&
    Number(candidate.level) >= 1 &&
    typeof candidate.started === 'boolean' &&
    typeof candidate.paused === 'boolean' &&
    typeof candidate.game_over === 'boolean' &&
    typeof candidate.demo_mode === 'boolean'
  )
}

function isCoordinate(value: unknown): value is [number, number] {
  return (
    Array.isArray(value) &&
    value.length === 2 &&
    Number.isInteger(value[0]) &&
    Number.isInteger(value[1])
  )
}

function send(message: object): void {
  if (socket?.readyState !== WebSocket.OPEN) {
    setConnectionStatus('disconnected', 'Input ignored — server unavailable')
    return
  }
  socket.send(JSON.stringify(message))
}

async function postGameAction(action: 'start' | 'pause' | 'resume'): Promise<void> {
  const response = await fetch(`/game/${action}`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Game server rejected ${action}: HTTP ${response.status}`)
  }

  const nextState: unknown = await response.json()
  if (!isGameState(nextState)) {
    throw new Error('The game server returned an invalid state.')
  }
  state = nextState
  render(nextState)
}

function turn(direction: Direction): void {
  if (state === null || !state.started || state.paused || state.game_over) {
    return
  }
  send({ direction })
}

function render(game: GameState): void {
  const cellWidth = canvas.width / game.width
  const cellHeight = canvas.height / game.height

  context.fillStyle = '#06140c'
  context.fillRect(0, 0, canvas.width, canvas.height)
  drawGrid(cellWidth, cellHeight)
  drawCell(game.food, cellWidth, cellHeight, '#ffb000', 0.22)

  game.snake.forEach((part, index) => {
    drawCell(part, cellWidth, cellHeight, index === 0 ? '#e8ffe8' : '#46f36b', 0.12)
  })

  score.textContent = game.score.toString().padStart(6, '0')
  level.textContent = game.level.toString()
  playerName.textContent = getPlayerName()
  pauseButton.disabled = !game.started || game.game_over
  pauseButton.textContent = game.paused ? 'RESUME' : 'PAUSE'

  if (game.demo_mode) {
    showOverlay('DEMO MODE', `Autoplaying at level ${game.level}`)
  } else if (!game.started) {
    showOverlay('READY?', 'Press New Game to begin')
  } else if (game.game_over) {
    showOverlay('GAME OVER', 'Press New Game to try again')
  } else if (game.paused) {
    showOverlay('PAUSED', 'Press Space or Resume to continue')
  } else {
    hideOverlay()
  }
}

function drawGrid(cellWidth: number, cellHeight: number): void {
  context.strokeStyle = 'rgba(70, 243, 107, 0.08)'
  context.lineWidth = 1
  context.beginPath()

  for (let x = 0; x <= canvas.width; x += cellWidth) {
    context.moveTo(x, 0)
    context.lineTo(x, canvas.height)
  }
  for (let y = 0; y <= canvas.height; y += cellHeight) {
    context.moveTo(0, y)
    context.lineTo(canvas.width, y)
  }
  context.stroke()
}

function drawCell(
  [x, y]: [number, number],
  width: number,
  height: number,
  color: string,
  insetRatio: number,
): void {
  const inset = Math.min(width, height) * insetRatio
  context.fillStyle = color
  context.fillRect(
    x * width + inset,
    y * height + inset,
    width - inset * 2,
    height - inset * 2,
  )
}

function getPlayerName(): string {
  const candidate = window.localStorage.getItem('snakebite.player-name')
  if (candidate !== null && candidate.trim() !== '') {
    return candidate.trim()
  }
  const defaultName = 'PLAYER'
  window.localStorage.setItem('snakebite.player-name', defaultName)
  return defaultName
}

function setPlayerName(name: string): void {
  const nextName = name.trim() || 'PLAYER'
  window.localStorage.setItem('snakebite.player-name', nextName)
  playerName.textContent = nextName
}

function showOverlay(title: string, message: string): void {
  overlayTitle.textContent = title
  overlayMessage.textContent = message
  overlay.hidden = false
}

function hideOverlay(): void {
  overlay.hidden = true
}

function showClientError(error: unknown): void {
  const message = error instanceof Error ? error.message : 'Unexpected client error'
  setConnectionStatus('disconnected', message)
  showOverlay('CLIENT ERROR', message)
}

const keyDirections: Readonly<Record<string, Direction>> = {
  ArrowUp: 'up',
  w: 'up',
  ArrowRight: 'right',
  d: 'right',
  ArrowDown: 'down',
  s: 'down',
  ArrowLeft: 'left',
  a: 'left',
}

window.addEventListener('keydown', (event) => {
  const direction = keyDirections[event.key]
  if (direction !== undefined) {
    event.preventDefault()
    turn(direction)
    return
  }
  if (event.code === 'Space') {
    event.preventDefault()
    void togglePause()
  }
})

document.querySelectorAll<HTMLButtonElement>('[data-direction]').forEach((button) => {
  button.addEventListener('click', () => {
    turn(button.dataset.direction as Direction)
  })
})

startButton.addEventListener('click', () => {
  void postGameAction('start').catch(showClientError)
})

pauseButton.addEventListener('click', () => {
  void togglePause()
})

async function togglePause(): Promise<void> {
  if (state === null || !state.started || state.game_over) {
    return
  }
  try {
    await postGameAction(state.paused ? 'resume' : 'pause')
  } catch (error) {
    showClientError(error)
  }
}

const namePrompt = window.prompt('Choose a player name', getPlayerName())
if (namePrompt !== null) {
  setPlayerName(namePrompt)
}

window.addEventListener('beforeunload', () => {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer)
  }
  socket?.close()
})

connect()
