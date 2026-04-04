/**
 * AudioManager — Web Audio API 기반 TTS 오디오 재생
 * Geny audioManager.ts 패턴 참고
 */

class AudioManager {
  private ctx: AudioContext | null = null;
  private gainNode: GainNode | null = null;
  private currentAudio: HTMLAudioElement | null = null;
  private _volume = 0.8;
  private _playing = false;

  init() {
    if (this.ctx) return;
    this.ctx = new AudioContext();
    this.gainNode = this.ctx.createGain();
    this.gainNode.gain.value = this._volume;
    this.gainNode.connect(this.ctx.destination);
  }

  get playing() { return this._playing; }
  get volume() { return this._volume; }

  setVolume(v: number) {
    this._volume = Math.max(0, Math.min(1, v));
    if (this.gainNode) this.gainNode.gain.value = this._volume;
  }

  async playBlob(blob: Blob): Promise<void> {
    this.stop();
    this.init();
    if (!this.ctx || !this.gainNode) return;

    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    this.currentAudio = audio;
    this._playing = true;

    // MediaElementSource → GainNode → destination
    const source = this.ctx.createMediaElementSource(audio);
    source.connect(this.gainNode);

    return new Promise<void>((resolve) => {
      audio.onended = () => {
        this._playing = false;
        URL.revokeObjectURL(url);
        resolve();
      };
      audio.onerror = () => {
        this._playing = false;
        URL.revokeObjectURL(url);
        resolve();
      };
      audio.play().catch(() => {
        this._playing = false;
        resolve();
      });
    });
  }

  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.currentTime = 0;
      this.currentAudio = null;
    }
    this._playing = false;
  }

  dispose() {
    this.stop();
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
      this.gainNode = null;
    }
  }
}

let _instance: AudioManager | null = null;
export function getAudioManager(): AudioManager {
  if (!_instance) _instance = new AudioManager();
  return _instance;
}
