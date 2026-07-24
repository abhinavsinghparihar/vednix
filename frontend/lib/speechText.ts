/**
 * Speech text utilities.
 *  - sanitizeForSpeech: markdown → clean speakable prose (code blocks become
 *    a spoken placeholder, tables flatten, syntax stripped)
 *  - detectSpeechLang: choose a TTS/STT locale per message (Devanagari → hi-IN)
 */

import type { Language } from "./ws";

const DEVANAGARI = /[\u0900-\u097F]/;

export function sanitizeForSpeech(markdown: string, maxChars = 4000): string {
  let text = markdown;

  // fenced code blocks → spoken placeholder
  text = text.replace(/```[\w-]*\n[\s\S]*?```/g, " (code snippet) ");
  // mermaid blocks → placeholder too
  text = text.replace(/\(code snippet\)/g, "(code snippet)");
  // inline code keeps its content
  text = text.replace(/`([^`]+)`/g, "$1");
  // images → alt text, links → their label
  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1");
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  // markdown table separator rows out
  text = text.replace(/^\s*\|[-\s|:]+\|\s*$/gm, " ");
  // pipes → commas so tables read naturally
  text = text.replace(/\|/g, ", ");
  // headings/emphasis/list markers
  text = text.replace(/^#{1,6}\s+/gm, "");
  text = text.replace(/(\*\*|__)(.*?)\1/g, "$2");
  text = text.replace(/(\*|_)(.*?)\1/g, "$2");
  text = text.replace(/^\s*[-*+]\s+/gm, "");
  text = text.replace(/^\s*\d+\.\s+/gm, "");
  // blockquotes/hr
  text = text.replace(/^>\s?/gm, "");
  text = text.replace(/^\s*[-_]{3,}\s*$/gm, ". ");
  // collapse whitespace
  text = text.replace(/\s{2,}/g, " ").trim();

  if (text.length > maxChars) {
    text = `${text.slice(0, maxChars)}… and more on screen.`;
  }
  return text;
}

/** Map a conversation language + message content to the best speech locale. */
export function detectSpeechLang(content: string, conversationLanguage: Language): string {
  if (conversationLanguage === "hi" || conversationLanguage === "hinglish") return "hi-IN";
  if (conversationLanguage === "en") return "en-US";
  // auto: sniff the message itself — Hinglish (roman) still sounds best on hi-IN
  if (DEVANAGARI.test(content)) return "hi-IN";
  return "en-US";
}
