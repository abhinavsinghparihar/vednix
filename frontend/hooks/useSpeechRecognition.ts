/**
 * STT hook — thin, safe wrapper over the browser's SpeechRecognition
 * (Chrome/Edge ship hi-IN recognition; feature-detected, never throws).
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type STTStatus = "idle" | "listening" | "unsupported" | "denied";

interface UseSTT {
  status: STTStatus;
  supported: boolean;
  start: (opts: {
    lang: string;
    onInterim: (interim: string) => void;
    onFinal: (finalText: string) => void;
  }) => void;
  stop: () => void;
}

export function useSpeechRecognition(): UseSTT {
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  // SSR-consistent: "idle" everywhere; real capability lands after mount
  // (this mismatch was React hydration error #418)
  const [status, setStatus] = useState<STTStatus>("idle");

  useEffect(() => {
    if (!(window.SpeechRecognition || window.webkitSpeechRecognition)) {
      setStatus("unsupported");
    }
    return () => recognitionRef.current?.abort();
  }, []);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setStatus((s) => (s === "listening" ? "idle" : s));
  }, []);

  const start = useCallback<UseSTT["start"]>(
    ({ lang, onInterim, onFinal }) => {
      const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
      if (!Ctor) {
        setStatus("unsupported");
        return;
      }
      // one recognizer at a time
      recognitionRef.current?.abort();

      const recognition = new Ctor();
      recognitionRef.current = recognition;
      recognition.lang = lang;
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => setStatus("listening");
      recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          const transcript = result[0]?.transcript ?? "";
          if (result.isFinal) onFinal(transcript);
          else interim += transcript;
        }
        if (interim) onInterim(interim);
      };
      recognition.onerror = (event) => {
        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          setStatus("denied");
        } else if (event.error !== "aborted") {
          setStatus("idle");
        }
      };
      recognition.onend = () => {
        recognitionRef.current = null;
        setStatus((s) => (s === "listening" ? "idle" : s));
      };

      try {
        recognition.start();
      } catch {
        recognitionRef.current = null;
        setStatus("idle");
      }
    },
    [],
  );

  return { status, supported: status !== "unsupported", start, stop };
}
