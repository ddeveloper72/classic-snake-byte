/**
 * Retro sound effects generated at runtime with the Web Audio API.
 *
 * Learning note:
 * The Apple IIe made sound by toggling a single speaker cone on and off, which
 * is why its games have that hard square-wave buzz. Synthesising square waves
 * here recreates that character, keeps the download free of audio assets, and
 * avoids shipping any copyrighted recordings from the original game.
 */

interface Tone {
  frequency: number
  duration: number
  type?: OscillatorType
}

/** Peak gain per note, kept low because square waves are harsh. */
const PEAK_GAIN = 0.05

export class SoundBoard {
  private context: AudioContext | null = null
  private muted = false

  get enabled(): boolean {
    return !this.muted
  }

  setEnabled(enabled: boolean): void {
    this.muted = !enabled
    if (enabled) {
      void this.resume()
    }
  }

  /**
   * Browsers refuse to start audio until the player interacts with the page,
   * so this must be called from inside a real user-gesture handler.
   */
  unlock(): void {
    void this.resume()
  }

  start(): void {
    this.play([
      { frequency: 392, duration: 0.07 },
      { frequency: 523, duration: 0.07 },
      { frequency: 784, duration: 0.12 },
    ])
  }

  eat(): void {
    this.play([
      { frequency: 880, duration: 0.05 },
      { frequency: 1319, duration: 0.06 },
    ])
  }

  levelUp(): void {
    this.play([
      { frequency: 523, duration: 0.08 },
      { frequency: 659, duration: 0.08 },
      { frequency: 784, duration: 0.08 },
      { frequency: 1047, duration: 0.16 },
    ])
  }

  gameOver(): void {
    this.play([
      { frequency: 311, duration: 0.14 },
      { frequency: 247, duration: 0.14 },
      { frequency: 196, duration: 0.3 },
    ])
  }

  turn(): void {
    // Steering feedback matters most to players who track the game by ear, but
    // it fires constantly, so it stays shorter and quieter than the rest.
    this.play([{ frequency: 180, duration: 0.025 }], PEAK_GAIN * 0.5)
  }

  /**
   * The rebound of a perilous plum.
   *
   * Learning note:
   * A plum can strike from off-screen attention, so this cue is pitched well
   * above the steering blip to warn players who are watching the snake's head
   * rather than the whole board.
   */
  plumBounce(): void {
    this.play(
      [
        { frequency: 660, duration: 0.03 },
        { frequency: 440, duration: 0.04 },
      ],
      PEAK_GAIN * 0.7,
    )
  }

  private play(tones: Tone[], gain: number = PEAK_GAIN): void {
    if (this.muted) {
      return
    }

    const context = this.ensureContext()
    if (context === null) {
      return
    }
    void this.resume()

    let startAt = context.currentTime
    for (const tone of tones) {
      const oscillator = context.createOscillator()
      const envelope = context.createGain()

      oscillator.type = tone.type ?? 'square'
      oscillator.frequency.setValueAtTime(tone.frequency, startAt)

      // A short attack and exponential release avoids the click that a raw
      // square wave produces when it starts or stops at full amplitude.
      envelope.gain.setValueAtTime(0.0001, startAt)
      envelope.gain.exponentialRampToValueAtTime(gain, startAt + 0.008)
      envelope.gain.exponentialRampToValueAtTime(0.0001, startAt + tone.duration)

      oscillator.connect(envelope)
      envelope.connect(context.destination)
      oscillator.start(startAt)
      oscillator.stop(startAt + tone.duration)

      startAt += tone.duration
    }
  }

  private ensureContext(): AudioContext | null {
    if (this.context !== null) {
      return this.context
    }
    if (typeof AudioContext === 'undefined') {
      return null
    }
    this.context = new AudioContext()
    return this.context
  }

  private async resume(): Promise<void> {
    if (this.context !== null && this.context.state === 'suspended') {
      try {
        await this.context.resume()
      } catch {
        // An unavailable audio device must never interrupt gameplay.
      }
    }
  }
}
