/**
 * Browser adapter for the server-authoritative Snakebite engine.
 *
 * Learning note:
 * Canvas is used instead of a game framework because Snakebite needs only a
 * small grid renderer. The backend remains authoritative: the browser sends
 * player intentions, then renders only state broadcast by the server.
 */
import './style.css'
import { SoundBoard } from './audio.ts'

type Direction = 'up' | 'right' | 'down' | 'left'
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface GameState {
  width: number
  height: number
  snake: [number, number][]
  foods: [number, number][]
  apples_remaining: number
  door_open: boolean
  door_x: number
  level_cleared: boolean
  level_elapsed_seconds: number
  speed_pressure_percent: number
  obstacles: [number, number][]
  plums: [number, number][]
  plum_bounced: boolean
  direction: Direction
  score: number
  level: number
  difficulty: number
  started: boolean
  paused: boolean
  game_over: boolean
  demo_mode: boolean
}

const CANVAS_WIDTH = 720
const CANVAS_HEIGHT = 480
const DIRECTIONS: readonly Direction[] = ['up', 'right', 'down', 'left']

/**
 * Pace options, slowest first.
 *
 * Learning note:
 * The original game only ever sped up, which locks out players whose reaction
 * time or hand-eye coordination has changed. Offering the pace as an explicit
 * choice keeps the arcade feel available without making it the only option.
 */
const DIFFICULTIES: readonly { value: number; label: string; hint: string }[] = [
  { value: 1, label: 'STROLL', hint: 'Gentlest pace — plenty of thinking time' },
  { value: 2, label: 'EASY', hint: 'Relaxed pace with room to recover' },
  { value: 3, label: 'STEADY', hint: 'A balanced, classic arcade pace' },
  { value: 4, label: 'BRISK', hint: 'Quick reactions needed' },
  { value: 5, label: 'SNAKEBITE', hint: 'Full 1981 arcade speed' },
]

const DEFAULT_DIFFICULTY = 1
const DIFFICULTY_STORAGE_KEY = 'snakebite.difficulty'
const SOUND_STORAGE_KEY = 'snakebite.sound'

/**
 * Perilous plum options, as the original's "HOW MANY PLUMS?" prompt offered.
 *
 * Learning note:
 * Plums are a difficulty dial that is independent of speed: a slow game with
 * two plums still demands board awareness, while zero plums keeps a fast game
 * purely about steering.
 */
const PLUM_OPTIONS: readonly { value: number; label: string; hint: string }[] = [
  { value: 0, label: 'NONE', hint: 'No plums — just you, the maze and the apples' },
  { value: 1, label: 'ONE', hint: 'A single plum bouncing around the board' },
  { value: 2, label: 'TWO', hint: 'Two plums — the full perilous experience' },
]

const DEFAULT_PLUMS = 0
const PLUMS_STORAGE_KEY = 'snakebite.plums'

/**
 * The keyboard layouts a player can choose between.
 *
 * Learning note:
 * Arrow keys suit one-handed play, while WASD suits players who rest their
 * left hand on the keyboard. Neither is correct for everyone, so the scheme is
 * a stored preference rather than a hard-coded assumption.
 */
type ControlScheme = 'arrows' | 'wasd' | 'both'

const CONTROL_SCHEMES: readonly {
  value: ControlScheme
  label: string
  keys: string
  hint: string
}[] = [
  {
    value: 'arrows',
    label: 'ARROWS',
    keys: '▲ ◀ ▼ ▶',
    hint: 'Steer with the arrow keys only',
  },
  {
    value: 'wasd',
    label: 'WASD',
    keys: 'W A S D',
    hint: 'W up, A left, S down, D right',
  },
  {
    value: 'both',
    label: 'EITHER',
    keys: '▲ + W',
    hint: 'Arrow keys and WASD both steer the snake',
  },
]

const DEFAULT_CONTROLS: ControlScheme = 'both'
const CONTROLS_STORAGE_KEY = 'snakebite.controls'

/** The direction each key produces, split by the scheme that owns it. */
const ARROW_KEYS: Readonly<Record<string, Direction>> = {
  arrowup: 'up',
  arrowright: 'right',
  arrowdown: 'down',
  arrowleft: 'left',
}

const WASD_KEYS: Readonly<Record<string, Direction>> = {
  w: 'up',
  d: 'right',
  s: 'down',
  a: 'left',
}

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <main class="shell">
    <header class="masthead">
      <div class="brand">
        <p class="eyebrow">Apple IIe spirit. Modern Python engine.</p>
        <h1>SNAKEBITE</h1>
      </div>
      <div class="score-panel" aria-live="polite">
        <div class="score-box">
          <span>PLAYER</span>
          <button type="button" id="player-name" class="player-name" title="Click to rename">PLAYER</button>
        </div>
        <div class="score-box">
          <span>SCORE</span>
          <strong id="score">000000</strong>
        </div>
        <div class="score-box">
          <span>LEVEL</span>
          <strong id="level">1</strong>
        </div>
        <div class="score-box">
          <span>APPLES</span>
          <strong id="apples">15</strong>
        </div>
        <div class="score-box">
          <span>PACE</span>
          <strong id="pace">BASE</strong>
        </div>
      </div>
    </header>

    <section class="game-frame" id="game-frame" aria-label="Snakebite game">
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
      <fieldset class="difficulty">
        <legend>Snake speed</legend>
        <div class="difficulty-options" role="radiogroup" aria-label="Snake speed">
          ${DIFFICULTIES.map(
            (option) => `
            <label class="difficulty-option">
              <input
                type="radio"
                name="difficulty"
                value="${option.value}"
                title="${option.hint}"
              />
              <span class="difficulty-number">${option.value}</span>
              <span class="difficulty-label">${option.label}</span>
            </label>`,
          ).join('')}
        </div>
        <p id="difficulty-hint" class="difficulty-hint" aria-live="polite"></p>
      </fieldset>

      <fieldset class="difficulty">
        <legend>Perilous plums</legend>
        <div class="difficulty-options" role="radiogroup" aria-label="Perilous plums">
          ${PLUM_OPTIONS.map(
            (option) => `
            <label class="difficulty-option">
              <input
                type="radio"
                name="plums"
                value="${option.value}"
                title="${option.hint}"
              />
              <span class="difficulty-number">${option.value}</span>
              <span class="difficulty-label">${option.label}</span>
            </label>`,
          ).join('')}
        </div>
        <p id="plums-hint" class="difficulty-hint" aria-live="polite"></p>
      </fieldset>

      <fieldset class="difficulty">
        <legend>Controls</legend>
        <div class="difficulty-options" role="radiogroup" aria-label="Control scheme">
          ${CONTROL_SCHEMES.map(
            (option) => `
            <label class="difficulty-option">
              <input
                type="radio"
                name="controls"
                value="${option.value}"
                title="${option.hint}"
              />
              <span class="difficulty-number control-keys">${option.keys}</span>
              <span class="difficulty-label">${option.label}</span>
            </label>`,
          ).join('')}
        </div>
        <p id="controls-hint" class="difficulty-hint" aria-live="polite"></p>
      </fieldset>

      <div class="button-row">
        <button id="start" class="primary" type="button">NEW GAME</button>
        <button id="pause" type="button" disabled>PAUSE</button>
        <button id="sound" type="button" aria-pressed="true">SOUND: ON</button>
      </div>
      <div class="direction-pad" aria-label="Direction controls">
        <button type="button" data-direction="up" aria-label="Move up">▲</button>
        <button type="button" data-direction="left" aria-label="Move left">◀</button>
        <button type="button" data-direction="down" aria-label="Move down">▼</button>
        <button type="button" data-direction="right" aria-label="Move right">▶</button>
      </div>
      <p class="instructions" id="instructions" aria-live="polite">
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
const gameFrame = requireElement<HTMLElement>('#game-frame')
const context = canvas.getContext('2d')
if (context === null) {
  throw new Error('This browser does not support the Canvas 2D API.')
}

const score = requireElement<HTMLElement>('#score')
const level = requireElement<HTMLElement>('#level')
const apples = requireElement<HTMLElement>('#apples')
const pace = requireElement<HTMLElement>('#pace')
const instructions = requireElement<HTMLElement>('#instructions')
const playerName = requireElement<HTMLButtonElement>('#player-name')
const overlay = requireElement<HTMLElement>('#overlay')
const overlayTitle = requireElement<HTMLElement>('#overlay-title')
const overlayMessage = requireElement<HTMLElement>('#overlay-message')
const connection = requireElement<HTMLElement>('#connection')
const startButton = requireElement<HTMLButtonElement>('#start')
const pauseButton = requireElement<HTMLButtonElement>('#pause')
const soundButton = requireElement<HTMLButtonElement>('#sound')
const difficultyHint = requireElement<HTMLElement>('#difficulty-hint')
const plumsHint = requireElement<HTMLElement>('#plums-hint')
const controlsHint = requireElement<HTMLElement>('#controls-hint')

const sounds = new SoundBoard()

let socket: WebSocket | null = null
let state: GameState | null = null
let reconnectTimer: number | null = null
/** Previous snapshot values, used to detect the moments worth sounding. */
let lastScore = 0
let lastLevel = 1
let lastDoorOpen = false
let lastGameOver = false
let lastPressurePercent = 0

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
    Array.isArray(candidate.foods) &&
    candidate.foods.every(isCoordinate) &&
    typeof candidate.apples_remaining === 'number' &&
    typeof candidate.door_open === 'boolean' &&
    typeof candidate.door_x === 'number' &&
    typeof candidate.level_cleared === 'boolean' &&
    typeof candidate.level_elapsed_seconds === 'number' &&
    Number(candidate.level_elapsed_seconds) >= 0 &&
    Number.isInteger(candidate.speed_pressure_percent) &&
    Number(candidate.speed_pressure_percent) >= 0 &&
    Number(candidate.speed_pressure_percent) <= 25 &&
    Array.isArray(candidate.obstacles) &&
    candidate.obstacles.every(isCoordinate) &&
    Array.isArray(candidate.plums) &&
    candidate.plums.every(isCoordinate) &&
    typeof candidate.plum_bounced === 'boolean' &&
    DIRECTIONS.includes(candidate.direction as Direction) &&
    Number.isInteger(candidate.score) &&
    Number(candidate.score) >= 0 &&
    Number.isInteger(candidate.level) &&
    Number(candidate.level) >= 1 &&
    Number.isInteger(candidate.difficulty) &&
    Number(candidate.difficulty) >= 1 &&
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
  const response = await fetch(`/game/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:
      action === 'start'
        ? JSON.stringify({ difficulty: getDifficulty(), plums: getPlums() })
        : undefined,
  })
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
  if (direction !== state.direction) {
    sounds.turn()
  }
  send({ direction })
}

/** Play the cues implied by the difference between two server snapshots. */
function announce(game: GameState): void {
  if (game.score > lastScore) {
    sounds.eat()
  }
  if (game.level_cleared || game.level > lastLevel) {
    sounds.levelUp()
  }
  if (game.door_open && !lastDoorOpen && !game.game_over) {
    sounds.doorOpen()
  }
  if (game.game_over && !lastGameOver) {
    sounds.gameOver()
  }
  if (game.plum_bounced && !game.game_over) {
    sounds.plumBounce()
  }
  if (
    game.speed_pressure_percent > lastPressurePercent &&
    !game.demo_mode &&
    !game.game_over
  ) {
    sounds.hurry()
  }

  lastScore = game.score
  lastLevel = game.level
  lastDoorOpen = game.door_open
  lastGameOver = game.game_over
  lastPressurePercent = game.speed_pressure_percent
}

function render(game: GameState): void {
  const cellWidth = canvas.width / game.width
  const cellHeight = canvas.height / game.height

  announce(game)

  context.fillStyle = '#06140c'
  context.fillRect(0, 0, canvas.width, canvas.height)
  drawGrid(cellWidth, cellHeight)

  game.obstacles.forEach((wall) => {
    drawWall(wall, cellWidth, cellHeight)
  })

  drawTopWall(game, cellWidth, cellHeight)

  game.foods.forEach((food) => drawApple(food, cellWidth, cellHeight))
  drawSnake(game, cellWidth, cellHeight)
  // Plums are drawn last so a plum crossing the snake stays visible.
  game.plums.forEach((plum) => {
    drawPlum(plum, cellWidth, cellHeight)
  })

  score.textContent = game.score.toString().padStart(6, '0')
  level.textContent = game.level.toString()
  apples.textContent = game.door_open ? 'EXIT' : game.apples_remaining.toString()
  pace.textContent =
    game.speed_pressure_percent === 0
      ? 'BASE'
      : `+${game.speed_pressure_percent}%`
  playerName.textContent = getPlayerName()

  // The door is easy to miss mid-game, so the hint line calls it out directly.
  if (game.door_open && !game.game_over) {
    instructions.textContent =
      'Apples cleared — escape through the glowing door in the top wall!'
  } else if (game.speed_pressure_percent > 0 && !game.demo_mode) {
    const atMaximum = game.speed_pressure_percent === 25
    instructions.textContent = atMaximum
      ? 'HURRY — maximum time pressure: snake speed +25%'
      : `HURRY — snake speed +${game.speed_pressure_percent}%; it rises every 20 seconds`
  } else {
    instructions.textContent = steeringHint()
  }
  pauseButton.disabled = !game.started || game.game_over
  pauseButton.textContent = game.paused ? 'RESUME' : 'PAUSE'

  if (game.demo_mode) {
    showOverlay('DEMO MODE', `Autoplaying at level ${game.level} — press New Game`)
  } else if (!game.started) {
    showOverlay('READY?', 'Choose a snake speed, then press New Game')
  } else if (game.game_over) {
    showOverlay('GAME OVER', `Scored ${game.score} — press New Game to retry`)
  } else if (game.paused) {
    showOverlay('PAUSED', 'Press Space or Resume to continue')
  } else {
    hideOverlay()
  }
}

/**
 * Draw a maze wall.
 *
 * Learning note:
 * The Apple IIe drew its level walls as plain white blocks, which read clearly
 * against the dark board. A highlight edge is added so walls stay legible for
 * players who find the flat original hard to pick out.
 */
function drawWall(
  [x, y]: [number, number],
  width: number,
  height: number,
): void {
  context.fillStyle = '#f4f8ff'
  context.fillRect(x * width, y * height, width, height)
  context.fillStyle = 'rgba(120, 170, 255, 0.45)'
  context.fillRect(x * width, y * height, width, Math.max(1, height * 0.2))
}

/**
 * Draw the top wall and, once the apple quota is cleared, the exit door in it.
 *
 * Learning note:
 * The door is the only route to the next level, so it is drawn as a literal
 * break in a solid wall with an arrow through it. Players should be able to
 * see where to go without reading any instructions.
 */
function drawTopWall(
  game: GameState,
  cellWidth: number,
  cellHeight: number,
): void {
  const thickness = Math.max(3, cellHeight * 0.22)
  const doorLeft = game.door_x * cellWidth
  const open = game.door_open

  context.fillStyle = '#2f7a4a'
  if (open) {
    context.fillRect(0, 0, doorLeft, thickness)
    context.fillRect(
      doorLeft + cellWidth,
      0,
      canvas.width - doorLeft - cellWidth,
      thickness,
    )
  } else {
    context.fillRect(0, 0, canvas.width, thickness)
  }

  if (!open) {
    return
  }

  // A pulsing glow makes the gap unmistakable against the grid behind it.
  const pulse = 0.55 + 0.45 * Math.sin(Date.now() / 180)
  context.save()
  context.fillStyle = '#7dffb0'
  context.globalAlpha = pulse
  context.fillRect(doorLeft, 0, cellWidth, thickness)

  const centerX = doorLeft + cellWidth / 2
  context.strokeStyle = '#7dffb0'
  context.lineWidth = Math.max(2, cellWidth * 0.14)
  context.beginPath()
  context.moveTo(centerX, cellHeight * 1.5)
  context.lineTo(centerX, thickness + 2)
  context.moveTo(centerX - cellWidth * 0.3, cellHeight * 0.55)
  context.lineTo(centerX, thickness + 2)
  context.lineTo(centerX + cellWidth * 0.3, cellHeight * 0.55)
  context.stroke()
  context.restore()
}

/** Draw the food as a round apple with a stem, as the original did. */
function drawApple(
  [x, y]: [number, number],
  width: number,
  height: number,
): void {
  const centerX = x * width + width / 2
  const centerY = y * height + height / 2
  const radius = Math.min(width, height) * 0.34

  context.fillStyle = '#ff4d4d'
  context.beginPath()
  context.arc(centerX, centerY + radius * 0.12, radius, 0, Math.PI * 2)
  context.fill()

  context.strokeStyle = '#7a4a1d'
  context.lineWidth = Math.max(1, radius * 0.22)
  context.beginPath()
  context.moveTo(centerX, centerY - radius * 0.55)
  context.lineTo(centerX + radius * 0.3, centerY - radius * 1.1)
  context.stroke()

  context.fillStyle = 'rgba(255, 255, 255, 0.75)'
  context.beginPath()
  context.arc(
    centerX - radius * 0.3,
    centerY - radius * 0.1,
    radius * 0.2,
    0,
    Math.PI * 2,
  )
  context.fill()
}

/**
 * Draw a perilous plum.
 *
 * Learning note:
 * The original rendered the plum in the Apple IIe's purple, which is the only
 * colour on the board that is neither snake green, apple red, nor wall white.
 * Keeping that separation means a plum can never be mistaken for food.
 */
function drawPlum(
  [x, y]: [number, number],
  width: number,
  height: number,
): void {
  const centerX = x * width + width / 2
  const centerY = y * height + height / 2
  const radius = Math.min(width, height) * 0.38

  // A soft halo keeps a fast-moving plum trackable at the higher speeds.
  context.fillStyle = 'rgba(199, 110, 255, 0.28)'
  context.beginPath()
  context.arc(centerX, centerY, radius * 1.45, 0, Math.PI * 2)
  context.fill()

  context.fillStyle = '#b44cff'
  context.beginPath()
  context.arc(centerX, centerY, radius, 0, Math.PI * 2)
  context.fill()

  // The crease down the middle is what reads as "plum" rather than "ball".
  context.strokeStyle = 'rgba(60, 0, 95, 0.85)'
  context.lineWidth = Math.max(1, radius * 0.16)
  context.beginPath()
  context.moveTo(centerX, centerY - radius * 0.85)
  context.lineTo(centerX, centerY + radius * 0.85)
  context.stroke()

  context.fillStyle = 'rgba(255, 255, 255, 0.8)'
  context.beginPath()
  context.arc(
    centerX - radius * 0.33,
    centerY - radius * 0.33,
    radius * 0.22,
    0,
    Math.PI * 2,
  )
  context.fill()
}

/** Draw the snake body, giving the head a visible facing direction. */
function drawSnake(game: GameState, width: number, height: number): void {
  game.snake.forEach((part, index) => {
    if (index === 0) {
      return
    }
    // Segments fade slightly toward the tail so the shape reads at a glance.
    const fade = Math.max(0.45, 1 - index / (game.snake.length * 1.6))
    context.fillStyle = `rgba(70, 243, 107, ${fade})`
    const inset = Math.min(width, height) * 0.12
    context.fillRect(
      part[0] * width + inset,
      part[1] * height + inset,
      width - inset * 2,
      height - inset * 2,
    )
  })

  const [headX, headY] = game.snake[0]
  const inset = Math.min(width, height) * 0.08
  context.fillStyle = '#e8ffe8'
  context.fillRect(
    headX * width + inset,
    headY * height + inset,
    width - inset * 2,
    height - inset * 2,
  )

  drawEyes(game.direction, headX * width, headY * height, width, height)
}

function drawEyes(
  direction: Direction,
  left: number,
  top: number,
  width: number,
  height: number,
): void {
  const radius = Math.max(1, Math.min(width, height) * 0.1)
  const near = 0.3
  const far = 0.7
  const ahead = 0.66

  const positions: Record<Direction, [number, number][]> = {
    up: [
      [near, 1 - ahead],
      [far, 1 - ahead],
    ],
    down: [
      [near, ahead],
      [far, ahead],
    ],
    left: [
      [1 - ahead, near],
      [1 - ahead, far],
    ],
    right: [
      [ahead, near],
      [ahead, far],
    ],
  }

  context.fillStyle = '#06140c'
  positions[direction].forEach(([offsetX, offsetY]) => {
    context.beginPath()
    context.arc(
      left + width * offsetX,
      top + height * offsetY,
      radius,
      0,
      Math.PI * 2,
    )
    context.fill()
  })
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

function getDifficulty(): number {
  const stored = Number(window.localStorage.getItem(DIFFICULTY_STORAGE_KEY))
  if (DIFFICULTIES.some((option) => option.value === stored)) {
    return stored
  }
  return DEFAULT_DIFFICULTY
}

function setDifficulty(value: number): void {
  const option =
    DIFFICULTIES.find((entry) => entry.value === value) ?? DIFFICULTIES[0]
  window.localStorage.setItem(DIFFICULTY_STORAGE_KEY, String(option.value))
  difficultyHint.textContent = `${option.label} — ${option.hint}`

  document
    .querySelectorAll<HTMLInputElement>('input[name="difficulty"]')
    .forEach((input) => {
      input.checked = Number(input.value) === option.value
    })
}

/** Read the stored plum count, falling back when storage holds junk. */
function getPlums(): number {
  const stored = Number(window.localStorage.getItem(PLUMS_STORAGE_KEY))
  if (PLUM_OPTIONS.some((option) => option.value === stored)) {
    return stored
  }
  return DEFAULT_PLUMS
}

/** Persist the plum count and sync the radio group and hint text to it. */
function setPlums(value: number): void {
  const option =
    PLUM_OPTIONS.find((entry) => entry.value === value) ?? PLUM_OPTIONS[0]
  window.localStorage.setItem(PLUMS_STORAGE_KEY, String(option.value))
  plumsHint.textContent = `${option.label} — ${option.hint}`

  document
    .querySelectorAll<HTMLInputElement>('input[name="plums"]')
    .forEach((input) => {
      input.checked = Number(input.value) === option.value
    })
}

/** Read the stored control scheme, falling back when storage holds junk. */
function getControlScheme(): ControlScheme {
  const stored = window.localStorage.getItem(CONTROLS_STORAGE_KEY)
  if (CONTROL_SCHEMES.some((option) => option.value === stored)) {
    return stored as ControlScheme
  }
  return DEFAULT_CONTROLS
}

/** Persist the control scheme and sync the radios, hint and help text. */
function setControlScheme(value: ControlScheme): void {
  const option =
    CONTROL_SCHEMES.find((entry) => entry.value === value) ?? CONTROL_SCHEMES[0]
  window.localStorage.setItem(CONTROLS_STORAGE_KEY, option.value)
  controlsHint.textContent = `${option.label} — ${option.hint}`

  document
    .querySelectorAll<HTMLInputElement>('input[name="controls"]')
    .forEach((input) => {
      input.checked = input.value === option.value
    })

  instructions.textContent = steeringHint()
}

/**
 * Resolve a keyboard event to a direction under the active scheme.
 *
 * Learning note:
 * The key is lower-cased first so Caps Lock or a held Shift cannot silently
 * disable WASD steering, which is a classic and very frustrating bug.
 */
function directionForKey(key: string): Direction | undefined {
  const normalized = key.toLowerCase()
  const scheme = getControlScheme()
  if (scheme !== 'wasd' && normalized in ARROW_KEYS) {
    return ARROW_KEYS[normalized]
  }
  if (scheme !== 'arrows' && normalized in WASD_KEYS) {
    return WASD_KEYS[normalized]
  }
  return undefined
}

/** Describe the steering keys the player actually chose. */
function steeringHint(): string {
  const scheme = getControlScheme()
  if (scheme === 'wasd') {
    return 'W A S D to steer • Space to pause'
  }
  if (scheme === 'arrows') {
    return 'Arrow keys to steer • Space to pause'
  }
  return 'Arrow keys or WASD to steer • Space to pause'
}

/**
 * Bring the board into view so play starts where the player is looking.
 *
 * Learning note:
 * On short windows the controls push the canvas above the fold, so a player
 * pressing New Game would be steering a snake they cannot see. Centring the
 * board removes that whole class of confusion.
 */
function focusGameBoard(): void {
  const stillness = window.matchMedia('(prefers-reduced-motion: reduce)')
  gameFrame.scrollIntoView({
    behavior: stillness.matches ? 'auto' : 'smooth',
    block: 'center',
  })
}

function setSoundEnabled(enabled: boolean): void {
  sounds.setEnabled(enabled)
  window.localStorage.setItem(SOUND_STORAGE_KEY, enabled ? 'on' : 'off')
  soundButton.textContent = enabled ? 'SOUND: ON' : 'SOUND: OFF'
  soundButton.setAttribute('aria-pressed', String(enabled))
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

// Embedded browsers and some privacy modes make window.prompt throw. Renaming
// is a convenience, so a failure here must never abort the rest of start-up.
function promptForPlayerName(): void {
  let answer: string | null = null
  try {
    answer = window.prompt('Choose a player name', getPlayerName())
  } catch {
    playerName.disabled = true
    playerName.title = 'Renaming is not supported in this browser'
    return
  }
  if (answer !== null) {
    setPlayerName(answer)
  }
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

window.addEventListener('keydown', (event) => {
  const direction = directionForKey(event.key)
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
  // Audio must be unlocked inside a real user gesture before any cue is heard.
  sounds.unlock()
  sounds.start()
  focusGameBoard()
  void postGameAction('start').catch(showClientError)
})

pauseButton.addEventListener('click', () => {
  void togglePause()
})

soundButton.addEventListener('click', () => {
  sounds.unlock()
  setSoundEnabled(!sounds.enabled)
})

document
  .querySelectorAll<HTMLInputElement>('input[name="difficulty"]')
  .forEach((input) => {
    input.addEventListener('change', () => {
      setDifficulty(Number(input.value))
    })
  })

document
  .querySelectorAll<HTMLInputElement>('input[name="plums"]')
  .forEach((input) => {
    input.addEventListener('change', () => {
      setPlums(Number(input.value))
    })
  })

document
  .querySelectorAll<HTMLInputElement>('input[name="controls"]')
  .forEach((input) => {
    input.addEventListener('change', () => {
      setControlScheme(input.value as ControlScheme)
    })
  })

playerName.addEventListener('click', () => {
  promptForPlayerName()
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

setPlayerName(getPlayerName())

setDifficulty(getDifficulty())
setPlums(getPlums())
setControlScheme(getControlScheme())
// Keyboard steering only reaches a board the player can see, so the first
// paint puts it in the middle of the window too.
focusGameBoard()
setSoundEnabled(window.localStorage.getItem(SOUND_STORAGE_KEY) !== 'off')

window.addEventListener('beforeunload', () => {
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer)
  }
  socket?.close()
})

connect()
