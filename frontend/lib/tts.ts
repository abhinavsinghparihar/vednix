/**
 * TTS manager — singleton around speechSynthesis (OS voices, works offline;
 * Windows/macOS ship Hindi voices, so no backend or downloads are required).
 * Voice selection prefers neural/natural hi-IN or en voices when available.
 */

type SpeakingListener = (speaking: boolean) => void;

class TTSManager {
  rate = 1.0;
  private speakingNow = false;
  private listeners = new Set<SpeakingListener>();
  private voices: SpeechSynthesisVoice[] = [];

  constructor() {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      const refresh = () => {
        this.voices = window.speechSynthesis.getVoices();
      };
      refresh();
      window.speechSynthesis.onvoiceschanged = refresh;
    }
  }

  get supported(): boolean {
    return typeof window !== "undefined" && "speechSynthesis" in window;
  }

  get speaking(): boolean {
    return this.speakingNow;
  }

  onSpeakingChange(cb: SpeakingListener): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private setSpeaking(v: boolean) {
    if (this.speakingNow === v) return;
    this.speakingNow = v;
    this.listeners.forEach((cb) => cb(v));
  }

  private pickVoice(lang: string): SpeechSynthesisVoice | null {
    if (!this.voices.length) return null;
    const exact = this.voices.filter((v) => v.lang === lang);
    const prefix = this.voices.filter((v) => v.lang.startsWith(lang.split("-")[0]));
    const pool = exact.length ? exact : prefix;
    if (!pool.length) return null;
    const score = (v: SpeechSynthesisVoice) => {
      const n = v.name.toLowerCase();
      let s = 0;
      if (n.includes("natural") || n.includes("neural")) s += 3;
      if (n.includes("google")) s += 2;
      if (n.includes("microsoft")) s += 1;
      if (v.localService) s += 1; // offline voice = matches Vednix philosophy
      return s;
    };
    return pool.sort((a, b) => score(b) - score(a))[0];
  }

  speak(text: string, lang: string): void {
    if (!this.supported || !text.trim()) return;
    window.speechSynthesis.cancel(); // one voice at a time — newest wins
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = this.rate;
    const voice = this.pickVoice(lang);
    if (voice) utterance.voice = voice;
    utterance.onend = () => this.setSpeaking(false);
    utterance.onerror = () => this.setSpeaking(false);
    this.setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  stop(): void {
    if (!this.supported) return;
    window.speechSynthesis.cancel();
    this.setSpeaking(false);
  }
}

export const tts = new TTSManager();
